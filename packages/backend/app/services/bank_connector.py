"""
Bank Sync Connector Architecture — FinMind
Pluggable connector system for bank integrations via Account Aggregator (AA) framework.

Supports:
- Abstract interface (BankConnector ABC)
- MockConnector for testing/development
- SetuAAConnector for real Indian bank integrations via Setu AA
- Extensible to any AA provider (Finvu, OneMoney, etc.)
"""

from __future__ import annotations

import uuid
import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Domain types
# ─────────────────────────────────────────────

class TransactionType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class ConsentStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass
class BankTransaction:
    """Normalised transaction produced by every connector."""
    transaction_id: str
    account_id: str
    amount: float
    currency: str
    transaction_type: TransactionType
    description: str
    date: date
    balance: Optional[float] = None
    category_hint: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class BankAccount:
    """Account metadata returned after a successful consent."""
    account_id: str
    masked_account_number: str
    bank_name: str
    ifsc: Optional[str]
    account_type: str          # SAVINGS, CURRENT, etc.
    currency: str = "INR"
    holder_name: Optional[str] = None


@dataclass
class ConsentHandle:
    """Tracks the AA consent lifecycle."""
    handle_id: str
    redirect_url: str
    status: ConsentStatus = ConsentStatus.PENDING
    artefact_id: Optional[str] = None  # filled after user approval


# ─────────────────────────────────────────────
# Abstract interface
# ─────────────────────────────────────────────

class BankConnector(ABC):
    """
    Abstract base class every bank connector must implement.

    Lifecycle:
        1. initiate_consent()  → redirect user to AA consent page
        2. confirm_consent()   → called after user approves (webhook / redirect)
        3. fetch_accounts()    → list linked accounts
        4. import_transactions() → full historical import
        5. refresh()           → incremental sync since last_synced_at
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the AA / bank provider."""

    @abstractmethod
    def initiate_consent(self, user_id: str, redirect_uri: str) -> ConsentHandle:
        """
        Start the consent flow.

        Returns a ConsentHandle whose redirect_url the caller should send
        the user to for approval.
        """

    @abstractmethod
    def confirm_consent(self, handle: ConsentHandle, session_data: dict) -> ConsentHandle:
        """
        Finalise the consent after the user returns from the AA portal.

        Updates handle.status and handle.artefact_id in-place and returns it.
        """

    @abstractmethod
    def fetch_accounts(self, handle: ConsentHandle) -> list[BankAccount]:
        """Return all accounts linked under the given consent."""

    @abstractmethod
    def import_transactions(
        self,
        handle: ConsentHandle,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransaction]:
        """
        Fetch all transactions for account_id in [from_date, to_date].

        Used for the initial full import.
        """

    @abstractmethod
    def refresh(
        self,
        handle: ConsentHandle,
        account_id: str,
        last_synced_at: date,
    ) -> list[BankTransaction]:
        """
        Incremental sync: fetch transactions since last_synced_at.

        Used for periodic background refreshes.
        """


# ─────────────────────────────────────────────
# Mock connector (development / testing)
# ─────────────────────────────────────────────

class MockConnector(BankConnector):
    """
    Fully in-memory connector for local development and automated tests.
    No external network calls — deterministic output.
    """

    provider_name = "MockBank"

    # Seed data — override in tests by subclassing or patching _seed_transactions
    _SEED_TRANSACTIONS = [
        ("TXN001", "DEBIT",  1200.00, "Swiggy order",         "Food"),
        ("TXN002", "DEBIT",  4500.00, "Amazon purchase",       "Shopping"),
        ("TXN003", "CREDIT", 85000.0, "Salary credit",         "Income"),
        ("TXN004", "DEBIT",  999.00,  "Netflix subscription",  "Entertainment"),
        ("TXN005", "DEBIT",  2300.00, "Electricity bill",      "Utilities"),
        ("TXN006", "CREDIT", 500.00,  "Cashback credit",       "Income"),
        ("TXN007", "DEBIT",  1500.00, "Petrol",                "Transport"),
        ("TXN008", "DEBIT",  750.00,  "Medical store",         "Health"),
    ]

    def initiate_consent(self, user_id: str, redirect_uri: str) -> ConsentHandle:
        handle_id = f"mock-handle-{uuid.uuid4().hex[:8]}"
        redirect_url = f"{redirect_uri}?handle={handle_id}&mock=true"
        logger.info("[MockConnector] Consent initiated handle=%s", handle_id)
        return ConsentHandle(handle_id=handle_id, redirect_url=redirect_url)

    def confirm_consent(self, handle: ConsentHandle, session_data: dict) -> ConsentHandle:
        handle.status = ConsentStatus.ACTIVE
        handle.artefact_id = f"mock-artefact-{uuid.uuid4().hex[:8]}"
        logger.info("[MockConnector] Consent confirmed artefact=%s", handle.artefact_id)
        return handle

    def fetch_accounts(self, handle: ConsentHandle) -> list[BankAccount]:
        return [
            BankAccount(
                account_id="mock-acc-001",
                masked_account_number="XXXX XXXX 4321",
                bank_name="MockBank India",
                ifsc="MOCK0001234",
                account_type="SAVINGS",
                currency="INR",
                holder_name="Mock User",
            )
        ]

    def import_transactions(
        self,
        handle: ConsentHandle,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransaction]:
        return self._build_transactions(account_id, from_date, to_date)

    def refresh(
        self,
        handle: ConsentHandle,
        account_id: str,
        last_synced_at: date,
    ) -> list[BankTransaction]:
        return self._build_transactions(account_id, last_synced_at, date.today())

    # ── helpers ──────────────────────────────

    def _build_transactions(self, account_id: str, from_date: date, to_date: date) -> list[BankTransaction]:
        """Generate deterministic transactions in the requested window."""
        results = []
        day_range = (to_date - from_date).days or 1

        for i, (txn_id, txn_type, amount, desc, category) in enumerate(self._SEED_TRANSACTIONS):
            day_offset = int((i / len(self._SEED_TRANSACTIONS)) * day_range)
            txn_date = date.fromordinal(from_date.toordinal() + day_offset)
            results.append(
                BankTransaction(
                    transaction_id=f"{txn_id}-{from_date.isoformat()}",
                    account_id=account_id,
                    amount=amount,
                    currency="INR",
                    transaction_type=TransactionType(txn_type),
                    description=desc,
                    date=txn_date,
                    category_hint=category,
                )
            )
        logger.info("[MockConnector] Returning %d mock transactions", len(results))
        return results


# ─────────────────────────────────────────────
# Setu Account Aggregator connector
# ─────────────────────────────────────────────

class SetuAAConnector(BankConnector):
    """
    Production connector for Indian banks via Setu AA (aa.setu.co).

    Implements the ReBIT AA spec:
    https://api.rebit.org.in/

    Required env / config:
        SETU_CLIENT_ID     — issued by Setu partner portal
        SETU_CLIENT_SECRET — used for HMAC-SHA256 request signing
        SETU_BASE_URL      — https://fiu-uat.setu.co (UAT) or prod URL
    """

    provider_name = "SetuAA"

    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "x-client-id": self._client_id,
        })

    # ── consent flow ─────────────────────────

    def initiate_consent(self, user_id: str, redirect_uri: str) -> ConsentHandle:
        payload = {
            "redirectUrl": redirect_uri,
            "vua": f"{user_id}@setu",          # virtual user address
            "consentTypes": ["TRANSACTIONS"],
            "fetchType": "PERIODIC",
            "frequency": {"unit": "MONTH", "value": 1},
            "dataRange": {"from": "2020-01-01", "to": date.today().isoformat()},
            "dataLife": {"unit": "YEAR", "value": 1},
            "purpose": {"code": "101", "text": "Personal finance management"},
        }
        self._sign(payload)
        resp = self._post("/consent", payload)
        handle_id = resp["id"]
        redirect_url = resp["url"]
        logger.info("[SetuAA] Consent initiated handle=%s", handle_id)
        return ConsentHandle(handle_id=handle_id, redirect_url=redirect_url)

    def confirm_consent(self, handle: ConsentHandle, session_data: dict) -> ConsentHandle:
        """
        Called from the OAuth-style redirect callback.
        session_data must contain 'consentHandleId' and optionally 'status'.
        """
        resp = self._get(f"/consent/{handle.handle_id}")
        api_status = resp.get("status", "PENDING").upper()
        handle.status = ConsentStatus[api_status] if api_status in ConsentStatus.__members__ else ConsentStatus.PENDING
        if handle.status == ConsentStatus.ACTIVE:
            handle.artefact_id = resp.get("consentId")
        logger.info("[SetuAA] Consent status=%s artefact=%s", handle.status, handle.artefact_id)
        return handle

    # ── data fetch ───────────────────────────

    def fetch_accounts(self, handle: ConsentHandle) -> list[BankAccount]:
        resp = self._get(f"/accounts/{handle.artefact_id}")
        accounts = []
        for acc in resp.get("accounts", []):
            accounts.append(BankAccount(
                account_id=acc["linkRefNumber"],
                masked_account_number=acc.get("maskedAccNumber", "XXXX"),
                bank_name=acc.get("FIType", "Unknown Bank"),
                ifsc=acc.get("ifscCode"),
                account_type=acc.get("accType", "SAVINGS"),
                currency="INR",
                holder_name=acc.get("holderName"),
            ))
        return accounts

    def import_transactions(
        self,
        handle: ConsentHandle,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransaction]:
        return self._fetch_fi_data(handle, account_id, from_date, to_date)

    def refresh(
        self,
        handle: ConsentHandle,
        account_id: str,
        last_synced_at: date,
    ) -> list[BankTransaction]:
        return self._fetch_fi_data(handle, account_id, last_synced_at, date.today())

    # ── internals ────────────────────────────

    def _fetch_fi_data(
        self,
        handle: ConsentHandle,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransaction]:
        payload = {
            "consentId": handle.artefact_id,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "linkRefNumber": [account_id],
        }
        self._sign(payload)

        # Initiate FI request and poll until READY
        resp = self._post("/FI/request", payload)
        session_id = resp["sessionId"]
        self._poll_until_ready(session_id)

        raw = self._get(f"/FI/fetch/{session_id}")
        return self._normalise(raw, account_id)

    def _poll_until_ready(self, session_id: str, max_attempts: int = 10) -> None:
        import time
        for attempt in range(max_attempts):
            resp = self._get(f"/FI/request/{session_id}")
            if resp.get("status") == "READY":
                return
            if resp.get("status") == "FAILED":
                raise RuntimeError(f"FI request failed for session {session_id}")
            time.sleep(2 ** attempt)  # exponential backoff
        raise TimeoutError(f"FI request {session_id} did not become READY in time")

    def _normalise(self, raw: dict, account_id: str) -> list[BankTransaction]:
        """Convert Setu AA response → list[BankTransaction]."""
        txns = []
        for fi in raw.get("FI", []):
            for record in fi.get("data", []):
                for txn in record.get("Transaction", []):
                    txns.append(BankTransaction(
                        transaction_id=txn.get("txnId", str(uuid.uuid4())),
                        account_id=account_id,
                        amount=float(txn.get("amount", 0)),
                        currency="INR",
                        transaction_type=TransactionType(txn.get("type", "DEBIT").upper()),
                        description=txn.get("narration", ""),
                        date=date.fromisoformat(txn["valueDate"][:10]),
                        balance=float(txn["currentBalance"]) if "currentBalance" in txn else None,
                        raw=txn,
                    ))
        logger.info("[SetuAA] Normalised %d transactions", len(txns))
        return txns

    def _sign(self, payload: dict) -> None:
        """Add HMAC-SHA256 signature header per Setu spec."""
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        sig = hmac.new(
            self._client_secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        self._session.headers["x-jws-signature"] = sig

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._base_url}{path}"
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()


# ─────────────────────────────────────────────
# Connector registry
# ─────────────────────────────────────────────

_REGISTRY: dict[str, type[BankConnector]] = {
    "mock": MockConnector,
    "setu": SetuAAConnector,
}

def get_connector(provider: str, **kwargs) -> BankConnector:
    """
    Factory function — resolves provider name to a connector instance.

    Usage:
        connector = get_connector("mock")
        connector = get_connector("setu",
                                  client_id=...,
                                  client_secret=...,
                                  base_url=...)
    """
    cls = _REGISTRY.get(provider.lower())
    if cls is None:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown bank provider '{provider}'. Available: {available}")
    return cls(**kwargs)

def register_connector(name: str, cls: type[BankConnector]) -> None:
    """Register a custom connector at runtime."""
    if not issubclass(cls, BankConnector):
        raise TypeError(f"{cls} must subclass BankConnector")
    _REGISTRY[name.lower()] = cls
