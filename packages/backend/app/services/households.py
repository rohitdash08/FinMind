from ..extensions import db
from ..models import HouseholdMember, HouseholdRole


def get_membership(user_id: int) -> HouseholdMember | None:
    return db.session.query(HouseholdMember).filter_by(user_id=user_id).first()


def get_household_ids(user_id: int) -> set[int]:
    rows = (
        db.session.query(HouseholdMember.household_id)
        .filter_by(user_id=user_id)
        .all()
    )
    return {household_id for (household_id,) in rows}


def is_household_member(user_id: int, household_id: int | None) -> bool:
    if household_id is None:
        return False
    return (
        db.session.query(HouseholdMember.id)
        .filter_by(user_id=user_id, household_id=household_id)
        .first()
        is not None
    )


def is_household_admin(user_id: int, household_id: int) -> bool:
    member = (
        db.session.query(HouseholdMember)
        .filter_by(user_id=user_id, household_id=household_id)
        .first()
    )
    return member is not None and member.role == HouseholdRole.ADMIN


def can_access_scope(
    user_id: int, owner_user_id: int, household_id: int | None
) -> bool:
    if household_id is None:
        return owner_user_id == user_id
    return is_household_member(user_id, household_id)


def get_household_member_user_ids(household_id: int | None) -> list[int]:
    if household_id is None:
        return []
    rows = (
        db.session.query(HouseholdMember.user_id)
        .filter_by(household_id=household_id)
        .all()
    )
    return [user_id for (user_id,) in rows]
