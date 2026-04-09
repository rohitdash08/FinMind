from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import PayeeMerchantAlias, Category
from app.schemas import PayeeMerchantAliasSchema
from http import HTTPStatus

payee_merchant_aliases_bp = Blueprint("payee_merchant_aliases", __name__)
payee_merchant_alias_schema = PayeeMerchantAliasSchema()
payee_merchant_aliases_schema = PayeeMerchantAliasSchema(many=True)


@payee_merchant_aliases_bp.route("/", methods=["POST"])
@jwt_required()
def create_payee_merchant_alias():
    """Create a new payee/merchant alias mapping.

    Allows mapping a 'raw_name' found in transactions to a user-defined 'canonical_name'.
    Optionally associates a category for automatic categorization.
    Ensures uniqueness of 'raw_name' per user (case-insensitive).
    """
    user_id = get_jwt_identity()
    data = request.get_json()

    try:
        alias_data = payee_merchant_alias_schema.load(data)
    except Exception as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST

    raw_name = alias_data["raw_name"]
    canonical_name = alias_data["canonical_name"]
    category_id = alias_data.get("category_id")

    # Check for existing alias with the same raw_name for this user (case-insensitive)
    existing_alias = PayeeMerchantAlias.query.filter(
        PayeeMerchantAlias.user_id == user_id,
        db.func.lower(PayeeMerchantAlias.raw_name) == db.func.lower(raw_name),
    ).first()

    if existing_alias:
        return (
            jsonify({"message": f"Alias '{raw_name}' already exists for this user."}),
            HTTPStatus.CONFLICT,
        )

    # Validate category_id if provided
    if category_id:
        category = Category.query.filter_by(id=category_id, user_id=user_id).first()
        if not category:
            return jsonify({"message": "Category not found or does not belong to user"}), HTTPStatus.BAD_REQUEST


    new_alias = PayeeMerchantAlias(
        user_id=user_id,
        raw_name=raw_name,
        canonical_name=canonical_name,
        category_id=category_id,
    )

    db.session.add(new_alias)
    db.session.commit()

    return (
        jsonify(payee_merchant_alias_schema.dump(new_alias)),
        HTTPStatus.CREATED,
    )


@payee_merchant_aliases_bp.route("/", methods=["GET"])
@jwt_required()
def list_payee_merchant_aliases():
    """List all payee/merchant aliases for the current user."""
    user_id = get_jwt_identity()
    aliases = PayeeMerchantAlias.query.filter_by(user_id=user_id).all()
    return jsonify(payee_merchant_aliases_schema.dump(aliases)), HTTPStatus.OK


@payee_merchant_aliases_bp.route("/<int:alias_id>", methods=["GET"])
@jwt_required()
def get_payee_merchant_alias(alias_id):
    """Get a specific payee/merchant alias by ID."""
    user_id = get_jwt_identity()
    alias = PayeeMerchantAlias.query.filter_by(
        id=alias_id, user_id=user_id
    ).first()

    if not alias:
        return jsonify({"message": "Alias not found"}), HTTPStatus.NOT_FOUND

    return jsonify(payee_merchant_alias_schema.dump(alias)), HTTPStatus.OK


@payee_merchant_aliases_bp.route("/<int:alias_id>", methods=["PATCH"])
@jwt_required()
def update_payee_merchant_alias(alias_id):
    """Update a payee/merchant alias.

    Allows updating the 'canonical_name' and 'category_id' for an existing alias.
    The 'raw_name' cannot be changed via this endpoint as it's the unique identifier for the alias mapping.
    """
    user_id = get_jwt_identity()
    alias = PayeeMerchantAlias.query.filter_by(
        id=alias_id, user_id=user_id
    ).first()

    if not alias:
        return jsonify({"message": "Alias not found"}), HTTPStatus.NOT_FOUND

    data = request.get_json()
    try:
        # Only allow updating canonical_name and category_id.
        # raw_name is considered immutable after creation for a given alias entry.
        update_data = {}
        if "canonical_name" in data:
            update_data["canonical_name"] = data["canonical_name"]
        if "category_id" in data:
            update_data["category_id"] = data["category_id"]

        # Validate incoming data types for allowed fields
        payee_merchant_alias_schema.load(update_data, partial=True)

    except Exception as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST

    if "canonical_name" in update_data:
        alias.canonical_name = update_data["canonical_name"]
    if "category_id" in update_data:
        # Validate category_id if provided
        if update_data["category_id"] is not None:
            category = Category.query.filter_by(id=update_data["category_id"], user_id=user_id).first()
            if not category:
                return jsonify({"message": "Category not found or does not belong to user"}), HTTPStatus.BAD_REQUEST
        alias.category_id = update_data["category_id"]


    db.session.commit()
    return jsonify(payee_merchant_alias_schema.dump(alias)), HTTPStatus.OK


@payee_merchant_aliases_bp.route("/<int:alias_id>", methods=["DELETE"])
@jwt_required()
def delete_payee_merchant_alias(alias_id):
    """Delete a payee/merchant alias."""
    user_id = get_jwt_identity()
    alias = PayeeMerchantAlias.query.filter_by(
        id=alias_id, user_id=user_id
    ).first()

    if not alias:
        return jsonify({"message": "Alias not found"}), HTTPStatus.NOT_FOUND

    db.session.delete(alias)
    db.session.commit()

    return jsonify({"message": "Alias deleted"}), HTTPStatus.OK
