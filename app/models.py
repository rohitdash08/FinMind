    def __repr__(self):
        return f"<Category {self.id} (name='{self.name}')>"


from sqlalchemy.schema import UniqueConstraint
class PayeeMerchantAlias(db.Model):
    __tablename__ = "payee_merchant_aliases"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    raw_name = db.Column(db.String(255), nullable=False)
    canonical_name = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = db.relationship("User", backref="payee_merchant_aliases")
    category = db.relationship("Category", backref="payee_merchant_aliases")

    __table_args__ = (
        UniqueConstraint("user_id", db.func.lower(raw_name), name="uq_user_raw_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "raw_name": self.raw_name,
            "canonical_name": self.canonical_name,
            "category_id": self.category_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self):
        return (
            f"<PayeeMerchantAlias {self.id} (user_id={self.user_id}, "
            f"raw='{self.raw_name}', canonical='{self.canonical_name}')>"
        )


class Bill(db.Model):
    __tablename__ = "bills"