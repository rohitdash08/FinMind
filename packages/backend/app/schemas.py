from marshmallow import Schema, fields, validate, post_dump, post_load, validates_schema, ValidationError
from app.models import User, Category, Bill
import uuid


class UserSchema(Schema):
    id = fields.UUID(dump_only=True)
    email = fields.Email(required=True)
    password = fields.String(load_only=True, required=True, validate=validate.Length(min=6))
    preferred_currency = fields.String(
        validate=validate.Length(min=3, max=3),
        metadata={"description": "3-letter currency code (e.g., USD, INR)"},
        missing="INR" # default on load if not provided
    )
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class CategorySchema(Schema):
    id = fields.UUID(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1))
    budget = fields.Float(
        allow_none=True,
        validate=validate.Range(min=0, error="Budget must be a non-negative number"),
        metadata={"description": "Optional budget for the category"},
    )
    budget_currency = fields.String(
        allow_none=True,
        validate=validate.Length(min=3, max=3),
        metadata={"description": "3-letter currency code for the budget (e.g., USD, INR)"},
    )
    current_month_spend = fields.Float(
        dump_only=True,
        metadata={"description": "Calculated total spend for the current month in budget_currency"},
        default=0.0 # This default is only for dump, actual value is computed
    )
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class BillSchema(Schema):
    id = fields.UUID(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1))
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    currency = fields.String(
        validate=validate.Length(min=3, max=3),
        metadata={"description": "3-letter currency code (e.g., USD, INR)"},
        missing="INR" # default on load if not provided (will be overridden by user pref in resource)
    )
    next_due_date = fields.Date(required=True)
    cadence = fields.String(
        required=True,
        validate=validate.OneOf(["MONTHLY", "QUARTERLY", "BIANNUALLY", "ANNUALLY"]),
    )
    channel_email = fields.Boolean(missing=False)
    channel_whatsapp = fields.Boolean(missing=False)
    autopay_enabled = fields.Boolean(missing=False)
    paid_date = fields.Date(allow_none=True, dump_only=True)
    category_id = fields.UUID(
        allow_none=True,
        metadata={"description": "ID of the category this bill belongs to"},
    )
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

