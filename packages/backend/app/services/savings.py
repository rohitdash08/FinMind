from datetime import datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models_savings import (
    GoalStatus,
    SavingsContribution,
    SavingsGoal,
    SavingsMilestone,
)

DEFAULT_MILESTONES = [25, 50, 75, 100]


class SavingsService:
    """Business logic for savings goals."""

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_amount(raw) -> Decimal | None:
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _create_default_milestones(goal_id: int) -> None:
        for pct in DEFAULT_MILESTONES:
            db.session.add(
                SavingsMilestone(goal_id=goal_id, percentage=pct)
            )

    @staticmethod
    def _check_milestones(goal: SavingsGoal) -> list[int]:
        """Mark milestones reached if threshold met. Returns list of newly reached percentages."""
        if float(goal.target_amount) <= 0:
            return []
        progress = float(goal.current_amount) / float(goal.target_amount) * 100
        newly_reached: list[int] = []
        for ms in goal.milestones.filter_by(reached=False).all():
            if progress >= ms.percentage:
                ms.reached = True
                ms.reached_at = datetime.utcnow()
                newly_reached.append(ms.percentage)
        return newly_reached

    # ── CRUD ─────────────────────────────────────────────────

    def list_goals(self, user_id: int) -> list[SavingsGoal]:
        return (
            SavingsGoal.query
            .filter_by(user_id=user_id)
            .order_by(SavingsGoal.created_at.desc())
            .all()
        )

    def create_goal(self, user_id: int, data: dict) -> tuple[SavingsGoal | None, str | None]:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name is required"

        target = self._parse_amount(data.get("target_amount"))
        if target is None or target <= 0:
            return None, "target_amount must be a positive number"

        currency = (data.get("currency") or "INR")[:10]

        deadline = None
        if data.get("deadline"):
            try:
                deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
            except ValueError:
                return None, "invalid deadline format, use YYYY-MM-DD"

        goal = SavingsGoal(
            user_id=user_id,
            name=name,
            target_amount=target,
            currency=currency,
            deadline=deadline,
        )
        db.session.add(goal)
        db.session.flush()  # get goal.id

        self._create_default_milestones(goal.id)
        db.session.commit()

        return goal, None

    def get_goal(self, user_id: int, goal_id: int) -> SavingsGoal | None:
        goal = db.session.get(SavingsGoal, goal_id)
        if not goal or goal.user_id != user_id:
            return None
        return goal

    def update_goal(self, user_id: int, goal_id: int, data: dict) -> tuple[SavingsGoal | None, str | None]:
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            return None, "not found"

        if goal.status == GoalStatus.ABANDONED.value:
            return None, "cannot update an abandoned goal"

        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                return None, "name cannot be empty"
            goal.name = name

        if "target_amount" in data:
            target = self._parse_amount(data.get("target_amount"))
            if target is None or target <= 0:
                return None, "target_amount must be a positive number"
            goal.target_amount = target

        if "currency" in data:
            goal.currency = (data.get("currency") or "INR")[:10]

        if "deadline" in data:
            if data["deadline"] is None:
                goal.deadline = None
            else:
                try:
                    goal.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
                except ValueError:
                    return None, "invalid deadline format, use YYYY-MM-DD"

        db.session.commit()
        return goal, None

    def delete_goal(self, user_id: int, goal_id: int) -> tuple[bool, str | None]:
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            return False, "not found"
        db.session.delete(goal)
        db.session.commit()
        return True, None

    # ── contributions ────────────────────────────────────────

    def contribute(
        self,
        user_id: int,
        goal_id: int,
        amount,
        notes: str | None = None,
    ) -> tuple[SavingsContribution | None, dict | None, str | None]:
        """Add a contribution. Returns (contribution, meta_dict, error)."""
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            return None, None, "not found"

        if goal.status == GoalStatus.ABANDONED.value:
            return None, None, "cannot contribute to an abandoned goal"

        if goal.status == GoalStatus.COMPLETED.value:
            return None, None, "goal is already completed"

        parsed = self._parse_amount(amount)
        if parsed is None or parsed <= 0:
            return None, None, "amount must be a positive number"

        contribution = SavingsContribution(
            goal_id=goal.id,
            amount=parsed,
            notes=(notes or "").strip() or None,
        )
        db.session.add(contribution)
        goal.current_amount = Decimal(str(goal.current_amount)) + parsed

        newly_reached = self._check_milestones(goal)

        # Auto-complete goal
        completed = False
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED.value
            completed = True

        db.session.commit()

        meta = {
            "new_milestones": newly_reached,
            "completed": completed,
        }
        return contribution, meta, None

    # ── summary ──────────────────────────────────────────────

    def get_summary(self, user_id: int) -> dict:
        goals = SavingsGoal.query.filter_by(user_id=user_id).all()
        total_target = Decimal("0")
        total_saved = Decimal("0")
        active = 0
        completed = 0
        abandoned = 0

        for g in goals:
            total_target += Decimal(str(g.target_amount))
            total_saved += Decimal(str(g.current_amount))
            if g.status == GoalStatus.ACTIVE.value:
                active += 1
            elif g.status == GoalStatus.COMPLETED.value:
                completed += 1
            elif g.status == GoalStatus.ABANDONED.value:
                abandoned += 1

        overall_pct = (
            round(float(total_saved / total_target * 100), 2)
            if total_target > 0
            else 0.0
        )

        return {
            "total_goals": len(goals),
            "active": active,
            "completed": completed,
            "abandoned": abandoned,
            "total_target": float(total_target),
            "total_saved": float(total_saved),
            "overall_progress_pct": overall_pct,
        }

    # ── abandon ──────────────────────────────────────────────

    def abandon_goal(self, user_id: int, goal_id: int) -> tuple[SavingsGoal | None, str | None]:
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            return None, "not found"

        if goal.status == GoalStatus.COMPLETED.value:
            return None, "cannot abandon a completed goal"

        if goal.status == GoalStatus.ABANDONED.value:
            return None, "goal is already abandoned"

        goal.status = GoalStatus.ABANDONED.value
        db.session.commit()
        return goal, None


# Module-level singleton
savings_service = SavingsService()
