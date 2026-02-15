from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class BankAccount:
    id: str
    name: str
    balance: float
    currency: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class BankTransaction:
    id: str
    account_id: str
    amount: float
    description: str
    date: str

    def to_dict(self) -> dict:
        return asdict(self)
