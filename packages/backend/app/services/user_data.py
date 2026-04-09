import logging
from ..extensions import db
from ..models import User, Expense, Bill, Category, Reminder
from ..services.cache import cache_delete_patterns

logger = logging.getLogger("finmind.user_data")


def export_user_data(user_id: int) -> dict:
    """
    Collects all personal data for a given user.
    """
    user = User.query.get(user_id)
    if not user:
        return {}

    user_data = user.to_dict()
    user_data["expenses"] = [e.to_dict() for e in user.expenses]
    user_data["bills"] = [b.to_dict() for b in user.bills]
    user_data["categories"] = [c.to_dict() for c in user.categories]
    user_data["reminders"] = [r.to_dict() for r in user.reminders]

    logger.info("User data export initiated for user_id=%s", user_id)
    return user_data


def delete_user_data(user_id: int) -> bool:
    """
    Permanently deletes all personal data for a given user.
    This includes the user account and all associated expenses, bills, categories, and reminders.
    """
    user = User.query.get(user_id)
    if not user:
        logger.warning("Attempted to delete non-existent user_id=%s", user_id)
        return False

    try:
        # Due to 'cascade="all, delete-orphan"' on relationships in User model,
        # deleting the user object will automatically delete associated data.
        db.session.delete(user)
        db.session.commit()

        # Invalidate all user-specific cache entries
        cache_delete_patterns(
            [f"user:{user_id}:*", f"insights:{user_id}:*"]
        )

        logger.info("Successfully deleted all data for user_id=%s", user_id)
        return True
    except Exception as e:
        db.session.rollback()
        logger.exception(
            "Failed to delete user data for user_id=%s: %s", user_id, e
        )
        return False
