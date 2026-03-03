from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Household, HouseholdMember, HouseholdRole, User
from ..services.households import is_household_admin, is_household_member

bp = Blueprint("households", __name__)


@bp.post("")
@jwt_required()
def create_household():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    household = Household(name=name, created_by=uid)
    db.session.add(household)
    db.session.flush()
    db.session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=uid,
            role=HouseholdRole.ADMIN.value,
        )
    )
    db.session.commit()
    return (
        jsonify(
            id=household.id,
            name=household.name,
            role=HouseholdRole.ADMIN.value,
        ),
        201,
    )


@bp.get("/my")
@jwt_required()
def my_households():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(HouseholdMember, Household)
        .join(Household, Household.id == HouseholdMember.household_id)
        .filter(HouseholdMember.user_id == uid)
        .order_by(Household.created_at.desc())
        .all()
    )
    return jsonify(
        households=[
            {
                "id": household.id,
                "name": household.name,
                "role": member.role,
                "created_at": household.created_at.isoformat(),
            }
            for member, household in rows
        ]
    )


@bp.get("/<int:household_id>")
@jwt_required()
def household_details(household_id: int):
    uid = int(get_jwt_identity())
    household = db.session.get(Household, household_id)
    if not household:
        return jsonify(error="not found"), 404
    if not is_household_member(uid, household_id):
        return jsonify(error="forbidden"), 403

    rows = (
        db.session.query(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .filter(HouseholdMember.household_id == household_id)
        .order_by(HouseholdMember.joined_at.asc())
        .all()
    )
    return jsonify(
        id=household.id,
        name=household.name,
        created_by=household.created_by,
        created_at=household.created_at.isoformat(),
        members=[
            {
                "user_id": user.id,
                "email": user.email,
                "role": member.role,
                "joined_at": member.joined_at.isoformat(),
            }
            for member, user in rows
        ],
    )


@bp.post("/<int:household_id>/members")
@jwt_required()
def add_member(household_id: int):
    uid = int(get_jwt_identity())
    household = db.session.get(Household, household_id)
    if not household:
        return jsonify(error="not found"), 404
    if not is_household_admin(uid, household_id):
        return jsonify(error="forbidden"), 403

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify(error="email required"), 400

    invited = db.session.query(User).filter(db.func.lower(User.email) == email).first()
    if not invited:
        return jsonify(error="user not found"), 404

    if is_household_member(invited.id, household_id):
        return jsonify(error="user already a member"), 409

    role = str(data.get("role") or HouseholdRole.MEMBER.value).upper().strip()
    if role not in {HouseholdRole.ADMIN.value, HouseholdRole.MEMBER.value}:
        return jsonify(error="invalid role"), 400

    membership = HouseholdMember(
        household_id=household_id,
        user_id=invited.id,
        role=role,
    )
    db.session.add(membership)
    db.session.commit()
    return (
        jsonify(
            household_id=household_id,
            user_id=invited.id,
            email=invited.email,
            role=role,
        ),
        201,
    )
