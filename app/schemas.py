from marshmallow import Schema, fields, validate

# Shared schemas
class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    email = fields.Email(required=True)
    preferred_currency = fields.Str(required=True, validate=validate.OneOf(["INR", "USD", "EUR", "GBP"]))
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PayeeMerchantAliasSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    raw_name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    canonical_name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    category_id = fields.Int(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)