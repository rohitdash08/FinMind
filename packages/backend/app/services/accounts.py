"""Business logic for multi-account management."""
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models import Account, AccountType

VALID_TYPES = {t.value for t in AccountType}


class AccountService:
    """Service layer for financial accounts."""

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_balance(raw) -> Decimal | None:
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _account_dict(a: Account) -> dict:
        return {
            "id": a.id,
            "name": a.name,
            "account_type": a.account_type,
            "institution": a.institution,
            "balance": float(a.balance),
            "currency": a.currency,
            "is_active": a.is_active,
            "created_at": a.created_at.isoformat(),
            "updated_at": a.updated_at.isoformat(),
        }

    # ── CRUD ─────────────────────────────────────────────────

    def list_accounts(self, user_id: int) -> list[dict]:
        accounts = (
            Account.query
            .filter_by(user_id=user_id)
            .order_by(Account.created_at.desc())
            .all()
        )
        return [self._account_dict(a) for a in accounts]

    def create_account(self, user_id: int, data: dict) -> tuple[Account | None, str | None]:
        name = (data.get("name") or "").strip()
        if not name:
            return None, "name is required"

        account_type = (data.get("account_type") or "").strip().lower()
        if not account_type:
            return None, "account_type is required"
        if account_type not in VALID_TYPES:
            return None, f"invalid account_type, must be one of: {', '.join(sorted(VALID_TYPES))}"

        balance = self._parse_balance(data.get("balance", 0))
        if balance is None:
            return None, "balance must be a valid number"
        if balance < 0:
            return None, "balance cannot be negative"

        currency = (data.get("currency") or "INR")[:10]
        institution = (data.get("institution") or "").strip() or None

        account = Account(
            user_id=user_id,
            name=name,
            account_type=account_type,
            institution=institution,
            balance=balance,
            currency=currency,
        )
        db.session.add(account)
        db.session.commit()
        return account, None

    def get_account(self, user_id: int, account_id: int) -> Account | None:
        account = db.session.get(Account, account_id)
        if not account or account.user_id != user_id:
            return None
        return account

    def update_account(self, user_id: int, account_id: int, data: dict) -> tuple[Account | None, str | None]:
        account = self.get_account(user_id, account_id)
        if not account:
            return None, "not found"

        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                return None, "name cannot be empty"
            account.name = name

        if "account_type" in data:
            account_type = (data.get("account_type") or "").strip().lower()
            if account_type not in VALID_TYPES:
                return None, f"invalid account_type, must be one of: {', '.join(sorted(VALID_TYPES))}"
            account.account_type = account_type

        if "balance" in data:
            balance = self._parse_balance(data.get("balance"))
            if balance is None:
                return None, "balance must be a valid number"
            if balance < 0:
                return None, "balance cannot be negative"
            account.balance = balance

        if "currency" in data:
            account.currency = (data.get("currency") or "INR")[:10]

        if "institution" in data:
            account.institution = (data.get("institution") or "").strip() or None

        if "is_active" in data:
            account.is_active = bool(data["is_active"])

        db.session.commit()
        return account, None

    def delete_account(self, user_id: int, account_id: int) -> tuple[bool, str | None]:
        account = self.get_account(user_id, account_id)
        if not account:
            return False, "not found"
        db.session.delete(account)
        db.session.commit()
        return True, None

    # ── summary ──────────────────────────────────────────────

    def get_summary(self, user_id: int) -> dict:
        accounts = Account.query.filter_by(user_id=user_id, is_active=True).all()
        total_balance = Decimal("0")
        by_type: dict[str, dict] = {}

        for a in accounts:
            bal = Decimal(str(a.balance))
            total_balance += bal
            if a.account_type not in by_type:
                by_type[a.account_type] = {"count": 0, "balance": Decimal("0")}
            by_type[a.account_type]["count"] += 1
            by_type[a.account_type]["balance"] += bal

        return {
            "total_accounts": len(accounts),
            "total_balance": float(total_balance),
            "by_type": {
                t: {"count": v["count"], "balance": float(v["balance"])}
                for t, v in by_type.items()
            },
        }


# Module-level singleton
account_service = AccountService()
