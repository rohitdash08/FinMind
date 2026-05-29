import csv
import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

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

bp = Blueprint("privacy", __name__)

DELETE_CONFIRMATION = "DELETE_MY_DATA"


@bp.get("/export")
@jwt_required()
def export_personal_data():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    db.session.add(AuditLog(user_id=uid, action="privacy.export"))
    db.session.commit()

    generated_at = datetime.utcnow()
    archive = _build_export_archive(user, generated_at)
    filename = f"finmind-data-export-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    return send_file(
        io.BytesIO(archive),
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@bp.delete("/me")
@jwt_required()
def delete_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    if data.get("confirm") != DELETE_CONFIRMATION:
        return (
            jsonify(error=f"confirm must be {DELETE_CONFIRMATION}"),
            400,
        )

    deleted_cache_keys = _delete_user_cache_keys(uid)
    revoked_refresh_sessions = _revoke_refresh_sessions(uid)
    deleted_records = _delete_user_owned_records(uid)
    anonymized_audits = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid)
        .update({AuditLog.user_id: None}, synchronize_session=False)
    )
    db.session.delete(user)
    db.session.add(
        AuditLog(
            user_id=None,
            action=(
                "privacy.delete.completed "
                f"records={sum(deleted_records.values())} "
                f"anonymized_audit_logs={anonymized_audits}"
            ),
        )
    )
    db.session.commit()

    return jsonify(
        message="account permanently deleted",
        deleted_records=deleted_records,
        anonymized_audit_logs=anonymized_audits,
        deleted_cache_keys=deleted_cache_keys,
        revoked_refresh_sessions=revoked_refresh_sessions,
    )


def _build_export_archive(user: User, generated_at: datetime) -> bytes:
    tables = _collect_user_tables(user.id)
    profile = {
        "id": user.id,
        "email": user.email,
        "preferred_currency": user.preferred_currency,
        "role": user.role,
        "created_at": _export_value(user.created_at),
    }
    manifest = {
        "format_version": 1,
        "generated_at": generated_at.isoformat() + "Z",
        "profile_fields": sorted(profile.keys()),
        "tables": {name: len(rows) for name, rows in tables.items()},
    }
    export_json = {
        "manifest": manifest,
        "profile": profile,
        "tables": tables,
    }

    out = io.BytesIO()
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        archive.writestr(
            "profile.json", json.dumps(profile, indent=2, sort_keys=True) + "\n"
        )
        archive.writestr(
            "data.json", json.dumps(export_json, indent=2, sort_keys=True) + "\n"
        )
        for table_name, rows in tables.items():
            archive.writestr(f"{table_name}.csv", _rows_to_csv(rows))
    return out.getvalue()


def _collect_user_tables(uid: int) -> dict[str, list[dict]]:
    return {
        "categories": _model_rows(
            Category, uid, ["id", "name", "created_at"], order_by=Category.id
        ),
        "expenses": _model_rows(
            Expense,
            uid,
            [
                "id",
                "category_id",
                "amount",
                "currency",
                "expense_type",
                "notes",
                "spent_at",
                "source_recurring_id",
                "created_at",
            ],
            order_by=Expense.id,
        ),
        "recurring_expenses": _model_rows(
            RecurringExpense,
            uid,
            [
                "id",
                "category_id",
                "amount",
                "currency",
                "expense_type",
                "notes",
                "cadence",
                "start_date",
                "end_date",
                "active",
                "created_at",
            ],
            order_by=RecurringExpense.id,
        ),
        "bills": _model_rows(
            Bill,
            uid,
            [
                "id",
                "name",
                "amount",
                "currency",
                "next_due_date",
                "cadence",
                "autopay_enabled",
                "channel_whatsapp",
                "channel_email",
                "active",
                "created_at",
            ],
            order_by=Bill.id,
        ),
        "reminders": _model_rows(
            Reminder,
            uid,
            ["id", "bill_id", "message", "send_at", "sent", "channel"],
            order_by=Reminder.id,
        ),
        "ad_impressions": _model_rows(
            AdImpression,
            uid,
            ["id", "placement", "created_at"],
            order_by=AdImpression.id,
        ),
        "user_subscriptions": _subscription_rows(uid),
        "audit_logs": _model_rows(
            AuditLog,
            uid,
            ["id", "action", "created_at"],
            order_by=AuditLog.id,
        ),
    }


def _model_rows(model, uid: int, fields: list[str], *, order_by) -> list[dict]:
    rows = db.session.query(model).filter(model.user_id == uid).order_by(order_by).all()
    return [
        {field: _export_value(getattr(row, field)) for field in fields} for row in rows
    ]


def _subscription_rows(uid: int) -> list[dict]:
    rows = (
        db.session.query(UserSubscription, SubscriptionPlan)
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
        .filter(UserSubscription.user_id == uid)
        .order_by(UserSubscription.id)
        .all()
    )
    return [
        {
            "id": subscription.id,
            "plan_id": subscription.plan_id,
            "plan_name": plan.name,
            "plan_price_cents": plan.price_cents,
            "plan_interval": plan.interval,
            "active": subscription.active,
            "started_at": _export_value(subscription.started_at),
        }
        for subscription, plan in rows
    ]


def _rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _export_value(value):
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _delete_user_owned_records(uid: int) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for table_name, model in [
        ("reminders", Reminder),
        ("expenses", Expense),
        ("recurring_expenses", RecurringExpense),
        ("bills", Bill),
        ("categories", Category),
        ("ad_impressions", AdImpression),
        ("user_subscriptions", UserSubscription),
    ]:
        deleted[table_name] = (
            db.session.query(model)
            .filter(model.user_id == uid)
            .delete(synchronize_session=False)
        )
    return deleted


def _revoke_refresh_sessions(uid: int) -> int:
    target_uid = str(uid)
    revoked = 0
    for key in redis_client.scan_iter(match="auth:refresh:*", count=100):
        if redis_client.get(key) == target_uid:
            redis_client.delete(key)
            revoked += 1
    return revoked


def _delete_user_cache_keys(uid: int) -> int:
    deleted = 0
    for pattern in [f"user:{uid}:*", f"insights:{uid}:*"]:
        for key in redis_client.scan_iter(match=pattern, count=100):
            redis_client.delete(key)
            deleted += 1
    return deleted
