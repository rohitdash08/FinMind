from datetime import date, datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    jwt_required,
    get_jwt_identity,
)
from ..extensions import db, redis_client
from ..models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    SubscriptionPlan,
    User,
    UserSubscription,
)
import logging
import time

bp = Blueprint("auth", __name__)
logger = logging.getLogger("finmind.auth")
AUDIT_EXPORT_ACTION = "USER_DATA_EXPORTED"
AUDIT_DELETE_ACTION = "USER_ACCOUNT_DELETED"
SUPPORTED_CURRENCIES = {
    "USD",
    "INR",
    "EUR",
    "GBP",
    "AED",
    "SGD",
    "AUD",
    "CAD",
    "JPY",
}


@bp.post("/register")
def register():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        logger.warning("Register missing email/password")
        return jsonify(error="email and password required"), 400
    if db.session.query(User).filter_by(email=email).first():
        logger.info("Register email already used: %s", email)
        return jsonify(error="email already used"), 409
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        preferred_currency="INR",
    )
    db.session.add(user)
    db.session.commit()
    logger.info("Registered user id=%s email=%s", user.id, email)
    return jsonify(message="registered"), 201


@bp.post("/login")
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        logger.warning("Login failed for email=%s", email)
        return jsonify(error="invalid credentials"), 401
    access = create_access_token(identity=str(user.id))
    refresh = create_refresh_token(identity=str(user.id))
    _store_refresh_session(refresh, str(user.id))
    logger.info("Login success user_id=%s", user.id)
    return jsonify(access_token=access, refresh_token=refresh)


@bp.get("/me")
@jwt_required()
def me():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    return jsonify(
        id=user.id,
        email=user.email,
        preferred_currency=user.preferred_currency or "INR",
    )


@bp.patch("/me")
@jwt_required()
def update_me():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "preferred_currency" in data:
        cur = str(data.get("preferred_currency") or "").upper().strip()
        if cur not in SUPPORTED_CURRENCIES:
            return jsonify(error="unsupported preferred_currency"), 400
        user.preferred_currency = cur
    db.session.commit()
    return jsonify(
        id=user.id,
        email=user.email,
        preferred_currency=user.preferred_currency or "INR",
    )


@bp.get("/export")
@bp.get("/export-data")
@jwt_required()
def export_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    categories = (
        db.session.query(Category)
        .filter(Category.user_id == uid)
        .order_by(Category.created_at.desc())
        .all()
    )
    expenses = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid)
        .order_by(Expense.spent_at.desc(), Expense.created_at.desc())
        .all()
    )
    recurring = (
        db.session.query(RecurringExpense)
        .filter(RecurringExpense.user_id == uid)
        .order_by(RecurringExpense.created_at.desc())
        .all()
    )
    bills = (
        db.session.query(Bill)
        .filter(Bill.user_id == uid)
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    reminders = (
        db.session.query(Reminder)
        .filter(Reminder.user_id == uid)
        .order_by(Reminder.send_at.asc())
        .all()
    )
    subscriptions = (
        db.session.query(UserSubscription, SubscriptionPlan)
        .outerjoin(SubscriptionPlan, SubscriptionPlan.id == UserSubscription.plan_id)
        .filter(UserSubscription.user_id == uid)
        .order_by(UserSubscription.started_at.desc())
        .all()
    )
    ad_impressions = (
        db.session.query(AdImpression)
        .filter(AdImpression.user_id == uid)
        .order_by(AdImpression.created_at.desc())
        .all()
    )

    _write_audit_log(uid, AUDIT_EXPORT_ACTION)
    db.session.commit()

    audit_logs = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    logger.info("Generated data export user_id=%s", uid)
    return jsonify(
        generated_at=datetime.utcnow().isoformat(),
        profile={
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "role": user.role,
            "created_at": _to_iso(user.created_at),
        },
        categories=[_category_to_dict(item) for item in categories],
        expenses=[_expense_to_dict(item) for item in expenses],
        recurring_expenses=[_recurring_to_dict(item) for item in recurring],
        bills=[_bill_to_dict(item) for item in bills],
        reminders=[_reminder_to_dict(item) for item in reminders],
        subscriptions=[
            _subscription_to_dict(subscription, plan)
            for subscription, plan in subscriptions
        ],
        ad_impressions=[_ad_impression_to_dict(item) for item in ad_impressions],
        audit_logs=[_audit_to_dict(item) for item in audit_logs],
    )


@bp.delete("/delete")
@bp.delete("/delete-account")
@jwt_required()
def delete_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404
    payload = request.get_json(silent=True) or {}
    if not _is_delete_confirmed(payload):
        return jsonify(error="confirmation required"), 400

    _write_audit_log(uid, AUDIT_DELETE_ACTION)
    db.session.query(Reminder).filter(Reminder.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(Expense).filter(Expense.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(RecurringExpense).filter(RecurringExpense.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(Bill).filter(Bill.user_id == uid).delete(synchronize_session=False)
    db.session.query(Category).filter(Category.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(UserSubscription).filter(UserSubscription.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(AdImpression).filter(AdImpression.user_id == uid).delete(
        synchronize_session=False
    )
    db.session.query(AuditLog).filter(AuditLog.user_id == uid).update(
        {AuditLog.user_id: None},
        synchronize_session=False,
    )
    db.session.delete(user)
    db.session.commit()

    revoked_count = _revoke_refresh_sessions(uid)
    logger.info(
        "Deleted account user_id=%s revoked_refresh_sessions=%s", uid, revoked_count
    )
    return jsonify(message="account deleted"), 200


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    jti = claims.get("jti")
    if not jti or not redis_client.get(_refresh_key(jti)):
        logger.warning("Refresh rejected: revoked/unknown token jti=%s", jti)
        return jsonify(error="refresh token revoked"), 401
    uid = get_jwt_identity()
    access = create_access_token(identity=str(uid))
    logger.info("Refreshed token for user_id=%s", uid)
    return jsonify(access_token=access)


@bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    claims = get_jwt()
    jti = claims.get("jti")
    if jti:
        redis_client.delete(_refresh_key(jti))
    return jsonify(message="logged out"), 200


def _refresh_key(jti: str) -> str:
    return f"auth:refresh:{jti}"


def _store_refresh_session(refresh_token: str, uid: str):
    payload = decode_token(refresh_token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = max(int(exp - time.time()), 1)
    redis_client.setex(_refresh_key(jti), ttl, uid)


def _revoke_refresh_sessions(uid: int) -> int:
    uid_str = str(uid)
    keys_to_delete: list[str] = []
    try:
        for key in redis_client.scan_iter(match=_refresh_key("*")):
            if redis_client.get(key) == uid_str:
                keys_to_delete.append(key)
        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
        return len(keys_to_delete)
    except Exception:
        logger.exception("Failed to revoke refresh sessions for user_id=%s", uid)
        return 0


def _write_audit_log(uid: int, action: str) -> None:
    db.session.add(AuditLog(user_id=uid, action=action))


def _is_delete_confirmed(payload: dict) -> bool:
    if _as_bool(payload.get("confirm")) or _as_bool(payload.get("confirmed")):
        return True
    confirmation = payload.get("confirmation")
    if isinstance(confirmation, str) and confirmation.strip().upper() == "DELETE":
        return True
    query_confirm = request.args.get("confirm")
    return _as_bool(query_confirm)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "delete"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _to_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _enum_value(value):
    return getattr(value, "value", value)


def _category_to_dict(item: Category) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "created_at": _to_iso(item.created_at),
    }


def _expense_to_dict(item: Expense) -> dict:
    return {
        "id": item.id,
        "category_id": item.category_id,
        "amount": float(item.amount),
        "currency": item.currency,
        "expense_type": item.expense_type,
        "notes": item.notes or "",
        "spent_at": _to_iso(item.spent_at),
        "created_at": _to_iso(item.created_at),
    }


def _recurring_to_dict(item: RecurringExpense) -> dict:
    return {
        "id": item.id,
        "category_id": item.category_id,
        "amount": float(item.amount),
        "currency": item.currency,
        "expense_type": item.expense_type,
        "notes": item.notes,
        "cadence": _enum_value(item.cadence),
        "start_date": _to_iso(item.start_date),
        "end_date": _to_iso(item.end_date),
        "active": bool(item.active),
        "created_at": _to_iso(item.created_at),
    }


def _bill_to_dict(item: Bill) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "amount": float(item.amount),
        "currency": item.currency,
        "next_due_date": _to_iso(item.next_due_date),
        "cadence": _enum_value(item.cadence),
        "autopay_enabled": bool(item.autopay_enabled),
        "channel_whatsapp": bool(item.channel_whatsapp),
        "channel_email": bool(item.channel_email),
        "active": bool(item.active),
        "created_at": _to_iso(item.created_at),
    }


def _reminder_to_dict(item: Reminder) -> dict:
    return {
        "id": item.id,
        "bill_id": item.bill_id,
        "message": item.message,
        "send_at": _to_iso(item.send_at),
        "sent": bool(item.sent),
        "channel": item.channel,
    }


def _subscription_to_dict(
    item: UserSubscription, plan: SubscriptionPlan | None
) -> dict:
    return {
        "id": item.id,
        "plan_id": item.plan_id,
        "active": bool(item.active),
        "started_at": _to_iso(item.started_at),
        "plan": {
            "name": plan.name,
            "price_cents": plan.price_cents,
            "interval": plan.interval,
        }
        if plan
        else None,
    }


def _ad_impression_to_dict(item: AdImpression) -> dict:
    return {
        "id": item.id,
        "placement": item.placement,
        "created_at": _to_iso(item.created_at),
    }


def _audit_to_dict(item: AuditLog) -> dict:
    return {
        "id": item.id,
        "action": item.action,
        "created_at": _to_iso(item.created_at),
    }
