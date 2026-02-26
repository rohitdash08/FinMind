"""Household models for shared family budgeting."""
from datetime import datetime
from enum import Enum
import secrets
from .extensions import db


class HouseholdRole(str, Enum):
    """Roles within a household."""
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class Household(db.Model):
    """Family/household group for shared budgeting."""
    __tablename__ = "households"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    invite_code = db.Column(db.String(32), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    owner = db.relationship("User", foreign_keys=[owner_id], backref="owned_households")
    members = db.relationship("HouseholdMember", back_populates="household", cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(16)
    
    def to_dict(self, include_members=False):
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "invite_code": self.invite_code,
            "created_at": self.created_at.isoformat()
        }
        if include_members:
            result["members"] = [m.to_dict() for m in self.members]
        return result


class HouseholdMember(db.Model):
    """Member relationship for household groups."""
    __tablename__ = "household_members"
    
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), default=HouseholdRole.MEMBER.value, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    household = db.relationship("Household", back_populates="members")
    user = db.relationship("User", backref="household_memberships")
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('household_id', 'user_id', name='uq_household_member'),
    )
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "household_id": self.household_id,
            "user_id": self.user_id,
            "email": self.user.email if self.user else None,
            "role": self.role,
            "joined_at": self.joined_at.isoformat()
        }
    
    def has_permission(self, required_role: HouseholdRole) -> bool:
        """Check if member has required permission level."""
        role_hierarchy = {
            HouseholdRole.MEMBER: 1,
            HouseholdRole.ADMIN: 2,
            HouseholdRole.OWNER: 3
        }
        current = role_hierarchy.get(HouseholdRole(self.role), 0)
        required = role_hierarchy.get(required_role, 0)
        return current >= required
