"""
Celery tasks for report generation with retry and monitoring.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from ..celery_config import celery_app
from ..extensions import db, redis_client
from ..models import Expense, Bill, User

logger = logging.getLogger("finmind.tasks.reports")


class ReportTask(Task):
    """Base task class for report operations."""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log report task failures."""
        logger.error(f"Report task {task_id} failed: {exc}", exc_info=True)
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(
    base=ReportTask,
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    queue="low_priority",
    time_limit=300,  # 5 minutes
    soft_time_limit=240,  # 4 minutes
)
def generate_weekly_report_task(self, user_id: int) -> dict:
    """
    Generate weekly financial summary report.
    
    Args:
        user_id: User ID to generate report for
        
    Returns:
        dict with report data
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return {"status": "error", "reason": "user_not_found"}
        
        # Calculate date range (last 7 days)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        
        # Fetch expenses
        expenses = Expense.query.filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date
        ).all()
        
        # Calculate metrics
        total_spent = sum(e.amount for e in expenses)
        expense_count = len(expenses)
        
        # Group by category
        category_breakdown: Dict[str, float] = {}
        for expense in expenses:
            category = expense.category.name if expense.category else "Uncategorized"
            category_breakdown[category] = category_breakdown.get(category, 0) + expense.amount
        
        # Upcoming bills
        upcoming_bills = Bill.query.filter(
            Bill.user_id == user_id,
            Bill.due_date >= end_date,
            Bill.due_date <= end_date + timedelta(days=7),
            Bill.is_paid == False
        ).all()
        
        total_upcoming = sum(b.amount for b in upcoming_bills)
        
        report_data = {
            "user_id": user_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_spent": total_spent,
                "expense_count": expense_count,
                "average_per_day": total_spent / 7 if expenses else 0,
                "upcoming_bills_total": total_upcoming,
                "upcoming_bills_count": len(upcoming_bills),
            },
            "category_breakdown": category_breakdown,
            "top_expenses": [
                {"amount": e.amount, "description": e.description, "date": e.date.isoformat()}
                for e in sorted(expenses, key=lambda x: x.amount, reverse=True)[:5]
            ],
            "upcoming_bills": [
                {"name": b.name, "amount": b.amount, "due_date": b.due_date.isoformat()}
                for b in upcoming_bills
            ],
        }
        
        # Cache report for 24 hours
        cache_key = f"report:weekly:{user_id}"
        redis_client.setex(cache_key, 86400, str(report_data))
        
        logger.info(f"Generated weekly report for user {user_id}")
        return {"status": "success", "report": report_data}
        
    except SoftTimeLimitExceeded:
        logger.warning(f"Weekly report generation timed out for user {user_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300)
        return {"status": "timeout", "error": "Report generation took too long"}
        
    except Exception as exc:
        logger.exception(f"Failed to generate weekly report for user {user_id}")
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 300
            raise self.retry(exc=exc, countdown=countdown)
        raise


@celery_app.task(
    base=ReportTask,
    bind=True,
    max_retries=2,
    default_retry_delay=600,  # 10 minutes
    queue="low_priority",
    time_limit=600,  # 10 minutes
    soft_time_limit=480,  # 8 minutes
)
def generate_monthly_digest_task(self, user_id: int, month: int, year: int) -> dict:
    """
    Generate comprehensive monthly financial digest.
    
    Args:
        user_id: User ID
        month: Month number (1-12)
        year: Year (e.g., 2026)
        
    Returns:
        dict with monthly digest data
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return {"status": "error", "reason": "user_not_found"}
        
        # Calculate date range
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        
        # Fetch all data
        expenses = Expense.query.filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date < end_date
        ).all()
        
        bills = Bill.query.filter(
            Bill.user_id == user_id,
            Bill.due_date >= start_date,
            Bill.due_date < end_date
        ).all()
        
        # Calculate comprehensive metrics
        total_expenses = sum(e.amount for e in expenses)
        total_bills = sum(b.amount for b in bills if b.is_paid)
        
        # Category analysis
        category_spending: Dict[str, Dict[str, Any]] = {}
        for expense in expenses:
            category = expense.category.name if expense.category else "Uncategorized"
            if category not in category_spending:
                category_spending[category] = {"total": 0, "count": 0}
            category_spending[category]["total"] += expense.amount
            category_spending[category]["count"] += 1
        
        # Day-of-week analysis
        dow_spending = [0] * 7
        for expense in expenses:
            dow_spending[expense.date.weekday()] += expense.amount
        
        digest_data = {
            "user_id": user_id,
            "period": {"month": month, "year": year},
            "summary": {
                "total_expenses": total_expenses,
                "total_bills_paid": total_bills,
                "expense_count": len(expenses),
                "bills_paid_count": len([b for b in bills if b.is_paid]),
                "average_expense": total_expenses / len(expenses) if expenses else 0,
            },
            "category_analysis": category_spending,
            "day_of_week_spending": {
                "monday": dow_spending[0],
                "tuesday": dow_spending[1],
                "wednesday": dow_spending[2],
                "thursday": dow_spending[3],
                "friday": dow_spending[4],
                "saturday": dow_spending[5],
                "sunday": dow_spending[6],
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Cache for 7 days
        cache_key = f"report:monthly:{user_id}:{year}:{month}"
        redis_client.setex(cache_key, 604800, str(digest_data))
        
        logger.info(f"Generated monthly digest for user {user_id}, {month}/{year}")
        return {"status": "success", "digest": digest_data}
        
    except SoftTimeLimitExceeded:
        logger.warning(f"Monthly digest generation timed out for user {user_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=600)
        return {"status": "timeout", "error": "Digest generation took too long"}
        
    except Exception as exc:
        logger.exception(f"Failed to generate monthly digest for user {user_id}")
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 600
            raise self.retry(exc=exc, countdown=countdown)
        raise


@celery_app.task(queue="low_priority")
def schedule_all_weekly_reports() -> dict:
    """
    Schedule weekly reports for all active users.
    Called by scheduled job.
    """
    users = User.query.all()
    scheduled = 0
    
    for user in users:
        # Schedule with 1 minute stagger to avoid thundering herd
        generate_weekly_report_task.apply_async(
            args=[user.id],
            countdown=scheduled * 60
        )
        scheduled += 1
    
    logger.info(f"Scheduled weekly reports for {scheduled} users")
    return {"scheduled": scheduled}
