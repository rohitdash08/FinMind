"""
Celery tasks for AI-powered features with retry and monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from ..celery_config import celery_app
from ..extensions import db, redis_client
from ..services.ai import generate_insights, process_receipt
from ..models import Expense

logger = logging.getLogger("finmind.tasks.ai")


class AITask(Task):
    """Base task class for AI operations."""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log AI task failures."""
        logger.error(f"AI task {task_id} failed: {exc}", exc_info=True)
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(
    base=AITask,
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="default",
    time_limit=120,
    soft_time_limit=90,
)
def generate_insights_task(self, user_id: int, period: str = "monthly") -> dict:
    """
    Generate AI insights for user with retry logic.
    
    Args:
        user_id: User ID to generate insights for
        period: Time period for insights (daily, weekly, monthly)
        
    Returns:
        dict with generated insights
    """
    cache_key = f"insights:{user_id}:{period}"
    
    try:
        # Check cache first
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"Returning cached insights for user {user_id}")
            return {"status": "cached", "data": cached}
        
        # Generate insights
        insights = generate_insights(user_id, period)
        
        # Cache results (1 hour TTL)
        redis_client.setex(cache_key, 3600, str(insights))
        
        logger.info(f"Generated insights for user {user_id}, period={period}")
        return {"status": "success", "data": insights}
        
    except SoftTimeLimitExceeded:
        logger.warning(f"Insights generation timed out for user {user_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60)
        return {"status": "timeout", "error": "Generation took too long"}
        
    except Exception as exc:
        logger.exception(f"Failed to generate insights for user {user_id}")
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 30
            raise self.retry(exc=exc, countdown=countdown)
        raise


@celery_app.task(
    base=AITask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="default",
    time_limit=180,
    soft_time_limit=120,
)
def process_expense_receipt_task(
    self, 
    expense_id: int, 
    receipt_url: str,
    ocr_provider: str = "openai"
) -> dict:
    """
    Process expense receipt image with OCR and AI extraction.
    
    Args:
        expense_id: Associated expense ID
        receipt_url: URL or path to receipt image
        ocr_provider: OCR provider to use (openai, gemini)
        
    Returns:
        dict with extracted data
    """
    try:
        # Fetch expense
        expense = Expense.query.get(expense_id)
        if not expense:
            return {"status": "error", "reason": "expense_not_found"}
        
        # Process receipt
        extracted_data = process_receipt(receipt_url, provider=ocr_provider)
        
        # Update expense with extracted data
        if extracted_data:
            if extracted_data.get("amount") and not expense.amount:
                expense.amount = extracted_data["amount"]
            if extracted_data.get("category") and not expense.category_id:
                expense.category_id = extracted_data["category"]
            if extracted_data.get("date") and not expense.date:
                expense.date = extracted_data["date"]
            if extracted_data.get("description") and not expense.description:
                expense.description = extracted_data["description"]
            
            expense.receipt_processed = True
            expense.receipt_data = extracted_data
            db.session.commit()
            
            logger.info(f"Processed receipt for expense {expense_id}")
            return {
                "status": "success",
                "expense_id": expense_id,
                "extracted_data": extracted_data,
            }
        else:
            return {"status": "failed", "reason": "extraction_failed"}
            
    except SoftTimeLimitExceeded:
        logger.warning(f"Receipt processing timed out for expense {expense_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60)
        return {"status": "timeout", "error": "Processing took too long"}
        
    except Exception as exc:
        logger.exception(f"Failed to process receipt for expense {expense_id}")
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(exc=exc, countdown=countdown)
        raise
