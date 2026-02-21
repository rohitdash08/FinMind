# Household models for shared family budgeting
from datetime import datetime
from .extensions import db


class Household(db.Model):
    """Family/household group for shared budgeting"""
    __tablename__ = "households"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    owner = db.relationship("User", foreign_keys=[owner_id], backref="owned_households")
    members = db.relationship("HouseholdMember", back_populates="household", cascade="all, delete-orphan")


class HouseholdMember(db.Model):
    """Member relationship for household groups"""
    __tablename__ = "household_members"
    
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), default="MEMBER", nullable=False)  # OWNER, ADMIN, MEMBER
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    household = db.relationship("Household", back_populates="members")
    user = db.relationship("User", backref="household_memberships")
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('household_id', 'user_id', name='uq_household_member'),
    )
