"""
Weekly Financial Digest Service

Generates smart weekly summaries with spending trends, income analysis,
notable transactions, and savings rate calculations.
"""

from datetime import date, timedelta, datetime
from typing import Any
from sqlalchemy import extract, func, and_, or_
from flask import current_app
import logging

from ..extensions import db
from ..models import Expense, Category, Bill, User
from ..services.reminders import send_email

logger = logging.getLogger("finmind.digest")


class WeeklyDigestService:
    """Service for generating and delivering weekly financial digests."""

    @staticmethod
    def get_week_bounds(reference_date: date | None = None) -> tuple[date, date]:
        """
        Get the start and end dates for the week containing reference_date.
        Week runs from Monday to Sunday.

        Args:
            reference_date: Date to get week bounds for. Defaults to today.

        Returns:
            Tuple of (week_start, week_end) dates
        """
        if reference_date is None:
            reference_date = date.today()

        # Monday is weekday 0, Sunday is 6
        days_since_monday = reference_date.weekday()
        week_start = reference_date - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)

        return week_start, week_end

    @staticmethod
    def get_previous_week_bounds(reference_date: date | None = None) -> tuple[date, date]:
        """
        Get the start and end dates for the previous week.

        Args:
            reference_date: Reference date. Defaults to today.

        Returns:
            Tuple of (week_start, week_end) dates for previous week
        """
        if reference_date is None:
            reference_date = date.today()

        current_week_start, _ = WeeklyDigestService.get_week_bounds(reference_date)
        prev_week_end = current_week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)

        return prev_week_start, prev_week_end

    @staticmethod
    def generate_weekly_summary(
        user_id: int,
        week_start: date | None = None,
        week_end: date | None = None,
    ) -> dict[str, Any]:
        """
        Generate a comprehensive weekly financial summary for a user.

        Args:
            user_id: User ID to generate summary for
            week_start: Start date of the week (inclusive). Defaults to current week.
            week_end: End date of the week (inclusive). Defaults to current week.

        Returns:
            Dictionary containing weekly summary data
        """
        if week_start is None or week_end is None:
            week_start, week_end = WeeklyDigestService.get_week_bounds()

        # Get previous week for comparison
        prev_week_start, prev_week_end = WeeklyDigestService.get_previous_week_bounds(
            week_start
        )

        summary = {
            "period": {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "generated_at": datetime.utcnow().isoformat(),
            },
            "summary": {
                "total_income": 0.0,
                "total_expenses": 0.0,
                "net_flow": 0.0,
                "savings_rate": 0.0,
                "transaction_count": 0,
            },
            "trends": {
                "income_change": 0.0,
                "expense_change": 0.0,
                "income_change_pct": 0.0,
                "expense_change_pct": 0.0,
            },
            "spending_by_category": [],
            "notable_transactions": [],
            "upcoming_bills": [],
            "insights": [],
        }

        # Current week data
        current_income, current_expenses, current_count = (
            WeeklyDigestService._get_week_financials(user_id, week_start, week_end)
        )

        # Previous week data for trends
        prev_income, prev_expenses, _ = WeeklyDigestService._get_week_financials(
            user_id, prev_week_start, prev_week_end
        )

        # Populate summary
        summary["summary"]["total_income"] = float(current_income)
        summary["summary"]["total_expenses"] = float(current_expenses)
        summary["summary"]["net_flow"] = float(current_income - current_expenses)
        summary["summary"]["transaction_count"] = current_count

        # Calculate savings rate
        if current_income > 0:
            savings_rate = ((current_income - current_expenses) / current_income) * 100
            summary["summary"]["savings_rate"] = round(savings_rate, 2)

        # Calculate trends
        summary["trends"]["income_change"] = float(current_income - prev_income)
        summary["trends"]["expense_change"] = float(current_expenses - prev_expenses)

        if prev_income > 0:
            summary["trends"]["income_change_pct"] = round(
                ((current_income - prev_income) / prev_income) * 100, 2
            )

        if prev_expenses > 0:
            summary["trends"]["expense_change_pct"] = round(
                ((current_expenses - prev_expenses) / prev_expenses) * 100, 2
            )

        # Spending by category
        summary["spending_by_category"] = WeeklyDigestService._get_category_breakdown(
            user_id, week_start, week_end
        )

        # Notable transactions (largest expenses and incomes)
        summary["notable_transactions"] = WeeklyDigestService._get_notable_transactions(
            user_id, week_start, week_end, limit=5
        )

        # Upcoming bills for next week
        summary["upcoming_bills"] = WeeklyDigestService._get_upcoming_bills(
            user_id, week_end + timedelta(days=1), days_ahead=7
        )

        # Generate insights
        summary["insights"] = WeeklyDigestService._generate_insights(summary)

        return summary

    @staticmethod
    def _get_week_financials(
        user_id: int, week_start: date, week_end: date
    ) -> tuple[float, float, int]:
        """Get total income, expenses, and transaction count for a week."""
        try:
            # Income
            income = (
                db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                    Expense.expense_type == "INCOME",
                )
                .scalar() or 0
            )

            # Expenses
            expenses = (
                db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                    Expense.expense_type != "INCOME",
                )
                .scalar() or 0
            )

            # Transaction count
            count = (
                db.session.query(func.count(Expense.id))
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                )
                .scalar() or 0
            )

            return float(income), float(expenses), int(count)

        except Exception as e:
            logger.error("Error getting week financials: %s", str(e))
            return 0.0, 0.0, 0

    @staticmethod
    def _get_category_breakdown(
        user_id: int, week_start: date, week_end: date
    ) -> list[dict[str, Any]]:
        """Get spending breakdown by category for the week."""
        try:
            rows = (
                db.session.query(
                    Expense.category_id,
                    func.coalesce(Category.name, "Uncategorized").label("category_name"),
                    func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
                    func.count(Expense.id).label("transaction_count"),
                )
                .outerjoin(
                    Category,
                    (Category.id == Expense.category_id)
                    & (Category.user_id == user_id),
                )
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                    Expense.expense_type != "INCOME",
                )
                .group_by(Expense.category_id, Category.name)
                .order_by(func.sum(Expense.amount).desc())
                .all()
            )

            total = sum(float(r.total_amount or 0) for r in rows)

            return [
                {
                    "category_id": r.category_id,
                    "category_name": r.category_name,
                    "amount": float(r.total_amount or 0),
                    "transaction_count": int(r.transaction_count or 0),
                    "share_pct": (
                        round((float(r.total_amount or 0) / total) * 100, 2)
                        if total > 0
                        else 0
                    ),
                }
                for r in rows
            ]

        except Exception as e:
            logger.error("Error getting category breakdown: %s", str(e))
            return []

    @staticmethod
    def _get_notable_transactions(
        user_id: int, week_start: date, week_end: date, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the most significant transactions (largest amounts)."""
        try:
            # Get largest expenses
            expenses = (
                db.session.query(Expense, Category.name)
                .outerjoin(
                    Category,
                    (Category.id == Expense.category_id)
                    & (Category.user_id == user_id),
                )
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                    Expense.expense_type != "INCOME",
                )
                .order_by(Expense.amount.desc())
                .limit(limit)
                .all()
            )

            # Get largest incomes
            incomes = (
                db.session.query(Expense, Category.name)
                .outerjoin(
                    Category,
                    (Category.id == Expense.category_id)
                    & (Category.user_id == user_id),
                )
                .filter(
                    Expense.user_id == user_id,
                    Expense.spent_at >= week_start,
                    Expense.spent_at <= week_end,
                    Expense.expense_type == "INCOME",
                )
                .order_by(Expense.amount.desc())
                .limit(limit)
                .all()
            )

            notable = []

            for exp, cat_name in expenses:
                notable.append({
                    "id": exp.id,
                    "type": "EXPENSE",
                    "amount": float(exp.amount),
                    "description": exp.notes or "Expense",
                    "category": cat_name or "Uncategorized",
                    "date": exp.spent_at.isoformat(),
                    "currency": exp.currency,
                })

            for inc, cat_name in incomes:
                notable.append({
                    "id": inc.id,
                    "type": "INCOME",
                    "amount": float(inc.amount),
                    "description": inc.notes or "Income",
                    "category": cat_name or "Uncategorized",
                    "date": inc.spent_at.isoformat(),
                    "currency": inc.currency,
                })

            # Sort by amount (absolute value) and return top transactions
            notable.sort(key=lambda x: abs(x["amount"]), reverse=True)
            return notable[:limit]

        except Exception as e:
            logger.error("Error getting notable transactions: %s", str(e))
            return []

    @staticmethod
    def _get_upcoming_bills(
        user_id: int, start_date: date, days_ahead: int = 7
    ) -> list[dict[str, Any]]:
        """Get upcoming bills for the next N days."""
        try:
            end_date = start_date + timedelta(days=days_ahead)

            bills = (
                db.session.query(Bill)
                .filter(
                    Bill.user_id == user_id,
                    Bill.active.is_(True),
                    Bill.next_due_date >= start_date,
                    Bill.next_due_date <= end_date,
                )
                .order_by(Bill.next_due_date.asc())
                .all()
            )

            return [
                {
                    "id": b.id,
                    "name": b.name,
                    "amount": float(b.amount),
                    "currency": b.currency,
                    "due_date": b.next_due_date.isoformat(),
                    "days_until_due": (b.next_due_date - date.today()).days,
                    "cadence": b.cadence.value,
                }
                for b in bills
            ]

        except Exception as e:
            logger.error("Error getting upcoming bills: %s", str(e))
            return []

    @staticmethod
    def _generate_insights(summary: dict[str, Any]) -> list[str]:
        """Generate actionable insights based on the weekly summary."""
        insights = []

        # Savings rate insights
        savings_rate = summary["summary"]["savings_rate"]
        if savings_rate >= 30:
            insights.append(
                f"Excellent savings rate of {savings_rate:.1f}%! "
                "You're on track for strong financial growth."
            )
        elif savings_rate >= 20:
            insights.append(
                f"Good savings rate of {savings_rate:.1f}%. "
                "Keep it up to build your financial cushion."
            )
        elif savings_rate >= 10:
            insights.append(
                f"Your savings rate is {savings_rate:.1f}%. "
                "Consider reducing discretionary spending to improve."
            )
        elif savings_rate > 0:
            insights.append(
                f"Savings rate is low at {savings_rate:.1f}%. "
                "Review your spending categories for potential cuts."
            )
        else:
            insights.append(
                "Your expenses exceeded income this week. "
                "Review your notable transactions for potential savings."
            )

        # Spending trend insights
        expense_change_pct = summary["trends"]["expense_change_pct"]
        if expense_change_pct > 20:
            insights.append(
                f"Spending increased {expense_change_pct:.1f}% compared to last week. "
                "Check your category breakdown for areas to cut back."
            )
        elif expense_change_pct < -20:
            insights.append(
                f"Great job! Spending decreased {abs(expense_change_pct):.1f}% "
                "from last week. Keep up the good work!"
            )

        # Income trend insights
        income_change_pct = summary["trends"]["income_change_pct"]
        if income_change_pct > 10:
            insights.append(
                f"Income is up {income_change_pct:.1f}% from last week."
            )
        elif income_change_pct < -10:
            insights.append(
                f"Income is down {abs(income_change_pct):.1f}% from last week. "
                "Plan accordingly if this trend continues."
            )

        # Top category insight
        if summary["spending_by_category"]:
            top_category = summary["spending_by_category"][0]
            insights.append(
                f"Your highest spending category was '{top_category['category_name']}' "
                f"at {top_category['amount']:.2f} ({top_category['share_pct']:.1f}% of total)."
            )

        # Upcoming bills insight
        upcoming_bills = summary["upcoming_bills"]
        if upcoming_bills:
            total_due = sum(b["amount"] for b in upcoming_bills)
            insights.append(
                f"You have {len(upcoming_bills)} bill(s) totaling "
                f"{total_due:.2f} due in the next 7 days."
            )

        return insights

    @staticmethod
    def get_currency_symbol(currency_code: str | None) -> str:
        """Return a display symbol for a currency code."""
        symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "JPY": "¥",
            "CNY": "¥",
            "INR": "₹",
            "KRW": "₩",
            "RUB": "₽",
            "TRY": "₺",
            "BRL": "R$",
            "CAD": "C$",
            "AUD": "A$",
            "CHF": "CHF ",
            "SEK": "kr ",
            "NOK": "kr ",
            "DKK": "kr ",
            "PLN": "zł ",
        }
        if not currency_code:
            return "$"
        return symbols.get(currency_code.upper(), f"{currency_code.upper()} ")

    @staticmethod
    def format_digest_email(
        summary: dict[str, Any], user: User
    ) -> tuple[str, str]:
        """
        Format the digest as email subject and body.

        Args:
            summary: Weekly summary dictionary
            user: User object

        Returns:
            Tuple of (subject, body)
        """
        week_start = summary["period"]["week_start"]
        week_end = summary["period"]["week_end"]

        subject = f"Your Weekly Financial Summary ({week_start} to {week_end})"
        currency_symbol = WeeklyDigestService.get_currency_symbol(
            getattr(user, "preferred_currency", None)
        )

        lines = [
            f"Hello {user.email},",
            "",
            f"Here's your weekly financial summary for {week_start} to {week_end}:",
            "",
            "═══════════════════════════════════════════════════",
            "OVERVIEW",
            "═══════════════════════════════════════════════════",
            f"  Total Income:      {currency_symbol}{summary['summary']['total_income']:,.2f}",
            f"  Total Expenses:    {currency_symbol}{summary['summary']['total_expenses']:,.2f}",
            f"  Net Flow:          {currency_symbol}{summary['summary']['net_flow']:,.2f}",
            f"  Savings Rate:      {summary['summary']['savings_rate']:.1f}%",
            f"  Transactions:      {summary['summary']['transaction_count']}",
            "",
            "═══════════════════════════════════════════════════",
            "WEEK OVER WEEK TRENDS",
            "═══════════════════════════════════════════════════",
        ]

        income_change = summary["trends"]["income_change"]
        income_change_pct = summary["trends"]["income_change_pct"]
        income_emoji = "↑" if income_change >= 0 else "↓"
        lines.append(
            f"  Income:   {income_emoji} {currency_symbol}{abs(income_change):,.2f} "
            f"({income_change_pct:+.1f}%)"
        )

        expense_change = summary["trends"]["expense_change"]
        expense_change_pct = summary["trends"]["expense_change_pct"]
        expense_emoji = "↓" if expense_change <= 0 else "↑"
        lines.append(
            f"  Expenses: {expense_emoji} {currency_symbol}{abs(expense_change):,.2f} "
            f"({expense_change_pct:+.1f}%)"
        )

        lines.extend([
            "",
            "═══════════════════════════════════════════════════",
            "SPENDING BY CATEGORY",
            "═══════════════════════════════════════════════════",
        ])

        for cat in summary["spending_by_category"][:5]:
            lines.append(
                f"  • {cat['category_name']}: {currency_symbol}{cat['amount']:,.2f} "
                f"({cat['share_pct']:.1f}%)"
            )

        if summary["notable_transactions"]:
            lines.extend([
                "",
                "═══════════════════════════════════════════════════",
                "NOTABLE TRANSACTIONS",
                "═══════════════════════════════════════════════════",
            ])

            for tx in summary["notable_transactions"][:5]:
                tx_emoji = "💰" if tx["type"] == "INCOME" else "💸"
                lines.append(
                    f"  {tx_emoji} {tx['description']}: {currency_symbol}{tx['amount']:,.2f} ({tx['date']})"
                )

        if summary["upcoming_bills"]:
            lines.extend([
                "",
                "═══════════════════════════════════════════════════",
                "UPCOMING BILLS",
                "═══════════════════════════════════════════════════",
            ])

            for bill in summary["upcoming_bills"]:
                days = bill["days_until_due"]
                days_text = "today" if days == 0 else f"in {days} day(s)"
                lines.append(
                    f"  • {bill['name']}: {currency_symbol}{bill['amount']:,.2f} (due {days_text})"
                )

        lines.extend([
            "",
            "═══════════════════════════════════════════════════",
            "INSIGHTS",
            "═══════════════════════════════════════════════════",
        ])

        for insight in summary["insights"]:
            lines.append(f"  💡 {insight}")

        lines.extend([
            "",
            "───────────────────────────────────────────────────",
            "Log in to FinMind to see more details and manage your finances.",
            "",
            "Best regards,",
            "The FinMind Team",
        ])

        return subject, "\n".join(lines)

    @staticmethod
    def send_digest_email(user_id: int, summary: dict[str, Any]) -> bool:
        """
        Send the weekly digest email to a user.

        Args:
            user_id: User ID to send to
            summary: Weekly summary dictionary

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            user = db.session.get(User, user_id)
            if not user:
                logger.warning("User %s not found for digest email", user_id)
                return False

            subject, body = WeeklyDigestService.format_digest_email(summary, user)

            # Use user's email
            success = send_email(user.email, subject, body)

            if success:
                logger.info("Weekly digest email sent to user %s", user_id)
            else:
                logger.warning("Failed to send weekly digest email to user %s", user_id)

            return success

        except Exception as e:
            logger.error("Error sending digest email: %s", str(e))
            return False

    @staticmethod
    def generate_and_send_all_digests() -> dict[str, Any]:
        """
        Generate and send weekly digests to all users.

        This is typically called by the scheduled task.

        Returns:
            Summary of digest generation results
        """
        results = {
            "total_users": 0,
            "digests_generated": 0,
            "emails_sent": 0,
            "errors": [],
        }

        try:
            # Get all active users
            users = db.session.query(User).all()
            results["total_users"] = len(users)

            week_start, week_end = WeeklyDigestService.get_week_bounds()

            for user in users:
                try:
                    summary = WeeklyDigestService.generate_weekly_summary(
                        user.id, week_start, week_end
                    )
                    results["digests_generated"] += 1

                    # Only send email if user has transactions this week
                    if summary["summary"]["transaction_count"] > 0:
                        if WeeklyDigestService.send_digest_email(user.id, summary):
                            results["emails_sent"] += 1

                except Exception as e:
                    error_msg = f"Error processing user {user.id}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            logger.info(
                "Weekly digest batch complete: %d generated, %d emails sent",
                results["digests_generated"],
                results["emails_sent"],
            )

        except Exception as e:
            error_msg = f"Error in digest batch: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        return results
