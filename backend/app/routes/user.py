import io
import json
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.audit_logger import log_action
from app.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


def _serialize_row(obj) -> dict:
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        result[col.name] = val
    return result


@router.get("/me/export", summary="Export all personal data (GDPR)")
def export_user_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_data = _serialize_row(current_user)
    user_data.pop("hashed_password", None)

    expenses = [
        _serialize_row(e)
        for e in getattr(current_user, "expenses", [])
    ]
    bills = [
        _serialize_row(b)
        for b in getattr(current_user, "bills", [])
    ]
    reminders = [
        _serialize_row(r)
        for r in getattr(current_user, "reminders", [])
    ]
    categories = [
        _serialize_row(c)
        for c in getattr(current_user, "categories", [])
    ]

    package = {
        "exported_at": datetime.utcnow().isoformat(),
        "user": user_data,
        "expenses": expenses,
        "bills": bills,
        "reminders": reminders,
        "categories": categories,
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("personal_data.json", json.dumps(package, indent=2))
    zip_buffer.seek(0)

    log_action(
        db=db,
        action="PII_EXPORT",
        user_id=current_user.id,
        user_email=current_user.email,
        entity="user",
        entity_id=current_user.id,
        metadata={"exported_at": datetime.utcnow().isoformat()},
        ip_address=request.client.host if request.client else None,
    )

    filename = f"personal_data_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete account and all personal data (GDPR)",
)
def delete_user_account(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    user_email = current_user.email
    ip = request.client.host if request.client else None

    for expense in list(getattr(current_user, "expenses", [])):
        db.delete(expense)

    for bill in list(getattr(current_user, "bills", [])):
        db.delete(bill)

    for reminder in list(getattr(current_user, "reminders", [])):
        db.delete(reminder)

    for category in list(getattr(current_user, "categories", [])):
        db.delete(category)

    db.delete(current_user)
    db.flush()

    log_action(
        db=db,
        action="PII_DELETE",
        user_id=None,
        user_email=user_email,
        entity="user",
        entity_id=user_id,
        metadata={
            "deleted_at": datetime.utcnow().isoformat(),
            "deleted_user_id": user_id,
            "deleted_user_email": user_email,
        },
        ip_address=ip,
    )

    db.commit()

    return {
        "detail": "Account and all associated personal data have been permanently deleted."
    }
