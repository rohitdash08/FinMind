from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.insights import build_weekly_digest

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/weekly-digest")
def weekly_digest(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a weekly financial digest for the authenticated user.

    The digest includes:
    - Expense totals and category breakdown for the last 7 days
    - Comparison with the previous 7-day window
    - Bill summary for the period
    - Auto-generated textual insights
    """
    try:
        digest = build_weekly_digest(db, current_user.id)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Failed to generate weekly digest") from exc

    return digest
