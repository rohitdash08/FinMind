"""
Celery beat schedule configuration.
Defines periodic tasks for FinMind.
"""

from celery.schedules import crontab
from .celery_config import celery_app

# Add beat schedule
celery_app.conf.beat_schedule = {
    # Process due reminders every minute
    "process-due-reminders": {
        "task": "app.tasks.reminders.process_due_reminders",
        "schedule": 60.0,  # Every 60 seconds
    },
    
    # Generate weekly reports every Sunday at 9 AM
    "generate-weekly-reports": {
        "task": "app.tasks.reports.schedule_all_weekly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_week=0),
    },
    
    # Cleanup old notification logs daily at 3 AM
    "cleanup-old-logs": {
        "task": "app.tasks.reminders.cleanup_old_reminders",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {"days": 30},
    },
}

celery_app.conf.timezone = "UTC"
