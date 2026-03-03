from ..extensions import db
from ..models import HouseholdMember


def household_ids_for_user(user_id: int) -> list[int]:
    rows = (
        db.session.query(HouseholdMember.household_id)
        .filter(HouseholdMember.user_id == user_id)
        .all()
    )
    return [int(row.household_id) for row in rows]


def is_household_member(user_id: int, household_id: int) -> bool:
    return (
        db.session.query(HouseholdMember.id)
        .filter(
            HouseholdMember.user_id == user_id,
            HouseholdMember.household_id == household_id,
        )
        .first()
        is not None
    )


def is_household_admin(user_id: int, household_id: int) -> bool:
    return (
        db.session.query(HouseholdMember.id)
        .filter(
            HouseholdMember.user_id == user_id,
            HouseholdMember.household_id == household_id,
            HouseholdMember.role == "ADMIN",
        )
        .first()
        is not None
    )
