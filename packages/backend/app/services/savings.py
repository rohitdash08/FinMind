import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models import SavingsGoal, GoalMilestone, GoalContribution

logger = logging.getLogger("finmind.savings")

# デフォルトのマイルストーン（25%, 50%, 75%, 100%）
DEFAULT_MILESTONES = [
    (25, "25% reached"),
    (50, "Halfway there!"),
    (75, "75% reached"),
    (100, "Goal completed!"),
]


def _parse_amount(raw) -> Decimal | None:
    """金額文字列をDecimalに変換する"""
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def create_goal(user_id: int, data: dict) -> dict:
    """ゴールを作成し、自動でマイルストーンを生成する"""
    target = _parse_amount(data.get("target_amount"))
    if target is None or target <= 0:
        raise ValueError("invalid target_amount")

    goal = SavingsGoal(
        user_id=user_id,
        name=str(data.get("name", "")).strip()[:200],
        description=(str(data.get("description", "")).strip()[:500] or None),
        target_amount=target,
        current_amount=Decimal("0.00"),
        currency=str(data.get("currency", "INR"))[:10],
        deadline=data.get("deadline"),
        icon=data.get("icon"),
        color=data.get("color"),
        is_completed=False,
    )
    db.session.add(goal)
    db.session.flush()  # IDを確定

    # デフォルトマイルストーンを生成
    for pct, name in DEFAULT_MILESTONES:
        ms = GoalMilestone(
            goal_id=goal.id,
            name=name,
            target_percentage=pct,
        )
        db.session.add(ms)

    db.session.commit()
    logger.info("Created savings goal id=%s user=%s name=%s", goal.id, user_id, goal.name)
    return goal_to_dict(goal)


def get_goals(user_id: int) -> list[dict]:
    """ユーザーの全ゴールを進捗情報付きで返す"""
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=user_id)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )
    return [goal_to_dict(g) for g in goals]


def get_goal(user_id: int, goal_id: int) -> dict | None:
    """ゴール詳細（マイルストーン・コントリビューション含む）を返す"""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    return goal_detail_to_dict(goal)


def update_goal(user_id: int, goal_id: int, data: dict) -> dict | None:
    """ゴール情報を更新する"""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None

    if "name" in data:
        goal.name = str(data["name"]).strip()[:200]
    if "description" in data:
        goal.description = (str(data["description"]).strip()[:500] or None)
    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None or target <= 0:
            raise ValueError("invalid target_amount")
        goal.target_amount = target
        # ターゲット変更時にマイルストーンを再チェック
        _check_milestones(goal)
    if "currency" in data:
        goal.currency = str(data["currency"])[:10]
    if "deadline" in data:
        goal.deadline = data["deadline"]
    if "icon" in data:
        goal.icon = data["icon"]
    if "color" in data:
        goal.color = data["color"]

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal_id, user_id)
    return goal_to_dict(goal)


def add_contribution(user_id: int, goal_id: int, amount_raw, note: str | None = None) -> dict | None:
    """コントリビューションを追加し、マイルストーンをチェックする"""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None

    amount = _parse_amount(amount_raw)
    if amount is None or amount <= 0:
        raise ValueError("invalid amount")

    contribution = GoalContribution(
        goal_id=goal.id,
        amount=amount,
        note=(str(note).strip()[:500] if note else None),
    )
    db.session.add(contribution)

    # current_amountを更新
    goal.current_amount = goal.current_amount + amount
    goal.updated_at = datetime.utcnow()

    # マイルストーンチェック
    _check_milestones(goal)

    # 100%達成チェック
    if goal.current_amount >= goal.target_amount:
        goal.is_completed = True

    db.session.commit()
    logger.info(
        "Added contribution goal=%s amount=%s new_total=%s",
        goal_id, amount, goal.current_amount
    )
    return goal_detail_to_dict(goal)


def _check_milestones(goal: SavingsGoal):
    """マイルストーンの到達チェック（閾値を超えたら reached_at を記録）"""
    if float(goal.target_amount) == 0:
        return
    progress_pct = (float(goal.current_amount) / float(goal.target_amount)) * 100
    milestones = (
        db.session.query(GoalMilestone)
        .filter_by(goal_id=goal.id)
        .all()
    )
    now = datetime.utcnow()
    for ms in milestones:
        if ms.reached_at is None and progress_pct >= ms.target_percentage:
            ms.reached_at = now


def delete_goal(user_id: int, goal_id: int) -> bool:
    """ゴールを削除する（カスケードでマイルストーン・コントリビューションも削除）"""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return False
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, user_id)
    return True


def get_savings_summary(user_id: int) -> dict:
    """ユーザーの全ゴールにわたるサマリーを返す"""
    goals = (
        db.session.query(SavingsGoal)
        .filter_by(user_id=user_id)
        .all()
    )

    total_target = sum(float(g.target_amount) for g in goals)
    total_saved = sum(float(g.current_amount) for g in goals)
    completed_count = sum(1 for g in goals if g.is_completed)
    in_progress_count = sum(1 for g in goals if not g.is_completed)

    return {
        "total_goals": len(goals),
        "completed_goals": completed_count,
        "in_progress_goals": in_progress_count,
        "total_target": round(total_target, 2),
        "total_saved": round(total_saved, 2),
        "overall_progress": (
            round((total_saved / total_target) * 100, 2) if total_target > 0 else 0
        ),
    }


def goal_to_dict(g: SavingsGoal) -> dict:
    """SavingsGoalモデルをdict化（サマリー用）"""
    target = float(g.target_amount)
    current = float(g.current_amount)
    progress = round((current / target) * 100, 2) if target > 0 else 0

    return {
        "id": g.id,
        "user_id": g.user_id,
        "name": g.name,
        "description": g.description,
        "target_amount": target,
        "current_amount": current,
        "progress": progress,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "icon": g.icon,
        "color": g.color,
        "is_completed": g.is_completed,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


def goal_detail_to_dict(g: SavingsGoal) -> dict:
    """SavingsGoalモデルをdict化（詳細 + マイルストーン + コントリビューション）"""
    base = goal_to_dict(g)

    milestones = (
        db.session.query(GoalMilestone)
        .filter_by(goal_id=g.id)
        .order_by(GoalMilestone.target_percentage.asc())
        .all()
    )
    base["milestones"] = [
        {
            "id": m.id,
            "name": m.name,
            "target_percentage": m.target_percentage,
            "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        }
        for m in milestones
    ]

    contributions = (
        db.session.query(GoalContribution)
        .filter_by(goal_id=g.id)
        .order_by(GoalContribution.contributed_at.desc())
        .all()
    )
    base["contributions"] = [
        {
            "id": c.id,
            "amount": float(c.amount),
            "note": c.note,
            "contributed_at": c.contributed_at.isoformat() if c.contributed_at else None,
        }
        for c in contributions
    ]

    return base
