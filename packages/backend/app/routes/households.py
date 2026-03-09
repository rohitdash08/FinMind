import secrets

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Household, HouseholdMember, HouseholdRole, User
from ..services.households import get_membership, is_household_admin

bp = Blueprint("households", __name__)


def _generate_invite_code() -> str:
    return secrets.token_hex(4).upper()


def _member_role_value(member: HouseholdMember) -> str:
    return member.role.value if hasattr(member.role, "value") else str(member.role)


def _household_payload(household: Household) -> dict:
    members = (
        db.session.query(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .filter(HouseholdMember.household_id == household.id)
        .order_by(HouseholdMember.created_at.asc())
        .all()
    )
    return {
        "id": household.id,
        "name": household.name,
        "invite_code": household.invite_code,
        "members": [
            {
                "user_id": member.user_id,
                "email": user.email,
                "role": _member_role_value(member),
            }
            for member, user in members
        ],
    }


@bp.post("")
@jwt_required()
def create_household():
    uid = int(get_jwt_identity())
    if get_membership(uid):
        return jsonify(error="already in a household"), 409

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    code = _generate_invite_code()
    while db.session.query(Household.id).filter_by(invite_code=code).first():
        code = _generate_invite_code()

    household = Household(name=name, invite_code=code, created_by=uid)
    db.session.add(household)
    db.session.flush()
    db.session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=uid,
            role=HouseholdRole.ADMIN,
        )
    )
    db.session.commit()
    return (
        jsonify(
            id=household.id,
            name=household.name,
            invite_code=household.invite_code,
        ),
        201,
    )


@bp.get("/current")
@jwt_required()
def get_current_household():
    uid = int(get_jwt_identity())
    membership = get_membership(uid)
    if not membership:
        return jsonify(error="household not found"), 404
    household = db.session.get(Household, membership.household_id)
    if not household:
        return jsonify(error="household not found"), 404
    return jsonify(_household_payload(household))


@bp.post("/join")
@jwt_required()
def join_household():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    invite_code = (data.get("invite_code") or "").strip().upper()
    if not invite_code:
        return jsonify(error="invite_code required"), 400
    household = db.session.query(Household).filter_by(invite_code=invite_code).first()
    if not household:
        return jsonify(error="household not found"), 404

    membership = get_membership(uid)
    if membership and membership.household_id != household.id:
        return jsonify(error="already in a household"), 409
    if membership and membership.household_id == household.id:
        return jsonify(household_id=household.id), 200

    db.session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=uid,
            role=HouseholdRole.MEMBER,
        )
    )
    db.session.commit()
    return jsonify(household_id=household.id), 200


@bp.post("/leave")
@jwt_required()
def leave_household():
    uid = int(get_jwt_identity())
    membership = get_membership(uid)
    if not membership:
        return jsonify(error="household not found"), 404

    member_count = (
        db.session.query(HouseholdMember)
        .filter_by(household_id=membership.household_id)
        .count()
    )
    if membership.role == HouseholdRole.ADMIN and member_count > 1:
        return jsonify(error="admin cannot leave while other members exist"), 400

    if member_count <= 1:
        household = db.session.get(Household, membership.household_id)
        if household:
            db.session.delete(household)
    else:
        db.session.delete(membership)
    db.session.commit()
    return jsonify(message="left household"), 200


@bp.delete("/members/<int:member_user_id>")
@jwt_required()
def remove_member(member_user_id: int):
    uid = int(get_jwt_identity())
    membership = get_membership(uid)
    if not membership:
        return jsonify(error="household not found"), 404
    if not is_household_admin(uid, membership.household_id):
        return jsonify(error="admin required"), 403
    if member_user_id == uid:
        return jsonify(error="use leave endpoint"), 400

    target = (
        db.session.query(HouseholdMember)
        .filter_by(household_id=membership.household_id, user_id=member_user_id)
        .first()
    )
    if not target:
        return jsonify(error="member not found"), 404

    db.session.delete(target)
    db.session.commit()
    return jsonify(message="removed"), 200
