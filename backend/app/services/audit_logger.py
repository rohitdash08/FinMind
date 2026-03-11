import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import AuditLog


def log_action(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    entity: Optional[str] = None,
    entity_id: Optional[int] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        entity=entity,
        entity_id=entity_id,
        metadata=json.dumps(metadata) if metadata else None,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
