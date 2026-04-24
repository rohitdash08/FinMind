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
    Reminder,
    RecurringExpense,
    User,
    UserSubscription,
)
import logging
import time

bp = Blueprint("auth", __name__)
logger = logging.getLogger("finmind.auth")
_refresh_session_fallback: dict[str, tuple[str, float]] = {}
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


@bp.get("/me/export")
@jwt_required()
def export_me():
    """Return a portable JSON package of the signed-in user's personal data."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    export_package = {
        "user": _serialize_user(user),
        "categories": [
            _serialize_category(row)
            for row in Category.query.filter_by(user_id=uid).all()
        ],
        "expenses": [
            _serialize_expense(row)
            for row in Expense.query.filter_by(user_id=uid).all()
        ],
        "recurring_expenses": [
            _serialize_recurring_expense(row)
            for row in RecurringExpense.query.filter_by(user_id=uid).all()
        ],
        "bills": [
            _serialize_bill(row) for row in Bill.query.filter_by(user_id=uid).all()
        ],
        "reminders": [
            _serialize_reminder(row)
            for row in Reminder.query.filter_by(user_id=uid).all()
        ],
        "ad_impressions": [
            _serialize_ad_impression(row)
            for row in AdImpression.query.filter_by(user_id=uid).all()
        ],
        "subscriptions": [
            _serialize_subscription(row)
            for row in UserSubscription.query.filter_by(user_id=uid).all()
        ],
    }
    db.session.add(AuditLog(user_id=uid, action="USER_DATA_EXPORTED"))
    db.session.commit()
    return jsonify(export_package), 200


@bp.delete("/me")
@jwt_required()
def delete_me():
    """Irreversibly delete the signed-in user's account and personal data."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Children first, because the current schema does not define ON DELETE CASCADE.
    for model in (
        Reminder,
        Bill,
        Expense,
        RecurringExpense,
        Category,
        AdImpression,
        UserSubscription,
    ):
        model.query.filter_by(user_id=uid).delete(synchronize_session=False)
    db.session.delete(user)
    db.session.add(AuditLog(user_id=None, action=f"USER_DATA_DELETED:{uid}"))
    db.session.commit()
    return jsonify(message="account and personal data deleted"), 200


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    jti = claims.get("jti")
    if not jti or not _refresh_session_exists(jti):
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
        _delete_refresh_session(jti)
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
    try:
        redis_client.setex(_refresh_key(jti), ttl, uid)
    except Exception as error:  # pragma: no cover - exercised when Redis is unavailable
        logger.warning(
            "Redis unavailable; using in-memory refresh session fallback: %s", error
        )
        _refresh_session_fallback[jti] = (uid, float(exp))


def _refresh_session_exists(jti: str) -> bool:
    try:
        return bool(redis_client.get(_refresh_key(jti)))
    except Exception as error:  # pragma: no cover - exercised when Redis is unavailable
        logger.warning(
            "Redis unavailable; checking in-memory refresh session fallback: %s", error
        )
        fallback = _refresh_session_fallback.get(jti)
        if not fallback:
            return False
        _uid, exp = fallback
        if exp <= time.time():
            _refresh_session_fallback.pop(jti, None)
            return False
        return True


def _delete_refresh_session(jti: str) -> None:
    try:
        redis_client.delete(_refresh_key(jti))
    except Exception as error:  # pragma: no cover - exercised when Redis is unavailable
        logger.warning(
            "Redis unavailable; deleting in-memory refresh session fallback: %s", error
        )
    _refresh_session_fallback.pop(jti, None)


def _iso(value):
    return value.isoformat() if value else None


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _iso(user.created_at),
    }


def _serialize_category(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "created_at": _iso(category.created_at),
    }


def _serialize_expense(expense: Expense) -> dict:
    return {
        "id": expense.id,
        "category_id": expense.category_id,
        "amount": str(expense.amount),
        "currency": expense.currency,
        "expense_type": expense.expense_type,
        "notes": expense.notes,
        "spent_at": _iso(expense.spent_at),
        "source_recurring_id": expense.source_recurring_id,
        "created_at": _iso(expense.created_at),
    }


def _serialize_recurring_expense(expense: RecurringExpense) -> dict:
    cadence = (
        expense.cadence.value if hasattr(expense.cadence, "value") else expense.cadence
    )
    return {
        "id": expense.id,
        "category_id": expense.category_id,
        "amount": str(expense.amount),
        "currency": expense.currency,
        "expense_type": expense.expense_type,
        "notes": expense.notes,
        "cadence": cadence,
        "start_date": _iso(expense.start_date),
        "end_date": _iso(expense.end_date),
        "active": expense.active,
        "created_at": _iso(expense.created_at),
    }


def _serialize_bill(bill: Bill) -> dict:
    cadence = bill.cadence.value if hasattr(bill.cadence, "value") else bill.cadence
    return {
        "id": bill.id,
        "name": bill.name,
        "amount": str(bill.amount),
        "currency": bill.currency,
        "next_due_date": _iso(bill.next_due_date),
        "cadence": cadence,
        "autopay_enabled": bill.autopay_enabled,
        "channel_whatsapp": bill.channel_whatsapp,
        "channel_email": bill.channel_email,
        "active": bill.active,
        "created_at": _iso(bill.created_at),
    }


def _serialize_reminder(reminder: Reminder) -> dict:
    return {
        "id": reminder.id,
        "bill_id": reminder.bill_id,
        "message": reminder.message,
        "send_at": _iso(reminder.send_at),
        "sent": reminder.sent,
        "channel": reminder.channel,
    }


def _serialize_ad_impression(ad_impression: AdImpression) -> dict:
    return {
        "id": ad_impression.id,
        "placement": ad_impression.placement,
        "created_at": _iso(ad_impression.created_at),
    }


def _serialize_subscription(subscription: UserSubscription) -> dict:
    return {
        "id": subscription.id,
        "plan_id": subscription.plan_id,
        "active": subscription.active,
        "started_at": _iso(subscription.started_at),
    }
