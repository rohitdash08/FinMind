"""Setu Account Aggregator connector.

Integrates with Setu's AA gateway (https://setu.co/account-aggregator)
to fetch real Indian bank data via the RBI Account Aggregator framework.

Required env vars:
    SETU_CLIENT_ID      — from Setu partner portal
    SETU_CLIENT_SECRET  — from Setu partner portal
    SETU_BASE_URL       — sandbox or production endpoint
"""

import logging
import uuid
from datetime import date, datetime
from typing import Any

import requests

from ..config import Settings
from . import (
    BankAccount,
    BankConnector,
    SyncResult,
    Transaction,
    register_connector,
)

logger = logging.getLogger("finmind.connectors.setu")

_settings = Settings()


def _setu_configured() -> bool:
    return bool(_settings.setu_client_id and _settings.setu_client_secret)


def _get_auth_headers() -> dict:
    return {
        "x-client-id": _settings.setu_client_id or "",
        "x-client-secret": _settings.setu_client_secret or "",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return (_settings.setu_base_url or "").rstrip("/")


@register_connector
class SetuAAConnector(BankConnector):
    """Setu Account Aggregator connector for real Indian bank data."""

    @property
    def provider_name(self) -> str:
        return "setu_aa"

    # -- consent flow ---------------------------------------------------------

    def create_consent(self, user_id: int, **kwargs: Any) -> dict:
        if not _setu_configured():
            raise RuntimeError(
                "Setu AA credentials not configured. "
                "Set SETU_CLIENT_ID and SETU_CLIENT_SECRET."
            )

        mobile = kwargs.get("mobile")
        if not mobile:
            raise ValueError("mobile number required for Setu AA consent")

        payload = {
            "Detail": {
                "consentStart": datetime.utcnow().isoformat() + "Z",
                "consentExpiry": "2099-12-31T23:59:59.999Z",
                "consentMode": "STORE",
                "fetchType": "PERIODIC",
                "consentTypes": ["TRANSACTIONS"],
                "fiTypes": ["DEPOSIT"],
                "DataConsumer": {"id": _settings.setu_client_id},
                "Customer": {"id": f"{mobile}@onemoney"},
                "Purpose": {
                    "code": "101",
                    "refUri": "https://api.rebit.org.in/aa/purpose/101.xml",
                    "text": "Wealth management service",
                    "Category": {"type": "string"},
                },
                "FIDataRange": {
                    "from": "2020-01-01T00:00:00.000Z",
                    "to": datetime.utcnow().isoformat() + "Z",
                },
                "DataLife": {"unit": "YEAR", "value": 5},
                "Frequency": {"unit": "DAY", "value": 1},
            },
            "redirectUrl": kwargs.get(
                "redirect_url", "https://finmind.app/bank-sync/callback"
            ),
        }

        resp = requests.post(
            f"{_base_url()}/consents",
            headers=_get_auth_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        handle = data.get("id") or data.get("ConsentHandle", "")
        redirect = data.get("url") or data.get("redirectUrl", "")

        logger.info("Setu consent created handle=%s user=%s", handle, user_id)
        return {
            "consent_handle": handle,
            "redirect_url": redirect,
            "status": "pending",
        }

    def check_consent_status(self, consent_handle: str, **kwargs: Any) -> str:
        if not _setu_configured():
            raise RuntimeError("Setu AA credentials not configured.")

        resp = requests.get(
            f"{_base_url()}/consents/{consent_handle}",
            headers=_get_auth_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_status = (data.get("status") or "").upper()

        if raw_status in ("ACTIVE", "APPROVED", "READY"):
            return "approved"
        if raw_status in ("REJECTED", "REVOKED", "EXPIRED"):
            return "rejected"
        return "pending"

    # -- data fetching --------------------------------------------------------

    def fetch_accounts(self, consent_handle: str, **kwargs: Any) -> list[BankAccount]:
        if not _setu_configured():
            raise RuntimeError("Setu AA credentials not configured.")

        session_id = self._create_data_session(
            consent_handle,
            kwargs.get("from_date", date(2020, 1, 1)),
            kwargs.get("to_date", date.today()),
        )

        resp = requests.get(
            f"{_base_url()}/sessions/{session_id}",
            headers=_get_auth_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        accounts: list[BankAccount] = []
        for acc in data.get("accounts", data.get("Accounts", [])):
            acc_id = acc.get("linkRefNumber") or acc.get("id", "")
            label = acc.get("maskedAccNumber", acc_id)
            fi_type = (acc.get("FIType") or "DEPOSIT").lower()
            acc_type = "savings" if "saving" in fi_type else "current"
            accounts.append(
                BankAccount(
                    account_id=acc_id,
                    label=label,
                    type=acc_type,
                    currency="INR",
                    meta=acc,
                )
            )
        return accounts

    def fetch_transactions(
        self,
        consent_handle: str,
        account_id: str,
        from_date: date,
        to_date: date,
        **kwargs: Any,
    ) -> SyncResult:
        if not _setu_configured():
            raise RuntimeError("Setu AA credentials not configured.")

        session_id = self._create_data_session(consent_handle, from_date, to_date)
        fi_data = self._fetch_fi_data(session_id)
        txns = self._parse_transactions(fi_data, account_id)

        return SyncResult(
            transactions=txns,
            cursor=to_date.isoformat(),
            has_more=False,
        )

    def refresh_transactions(
        self,
        consent_handle: str,
        account_id: str,
        cursor: str | None,
        **kwargs: Any,
    ) -> SyncResult:
        if cursor:
            from_dt = date.fromisoformat(cursor)
        else:
            from_dt = date.today().replace(day=1)
        to_dt = date.today()

        return self.fetch_transactions(consent_handle, account_id, from_dt, to_dt)

    # -- internal helpers -----------------------------------------------------

    def _create_data_session(
        self,
        consent_handle: str,
        from_date: date,
        to_date: date,
    ) -> str:
        payload = {
            "consentId": consent_handle,
            "DataRange": {
                "from": f"{from_date.isoformat()}T00:00:00.000Z",
                "to": f"{to_date.isoformat()}T23:59:59.999Z",
            },
            "format": "json",
        }
        resp = requests.post(
            f"{_base_url()}/sessions",
            headers=_get_auth_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("id") or data.get("sessionId", "")

    def _fetch_fi_data(self, session_id: str) -> dict:
        resp = requests.get(
            f"{_base_url()}/sessions/{session_id}/data",
            headers=_get_auth_headers(),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_transactions(self, fi_data: dict, account_id: str) -> list[Transaction]:
        txns: list[Transaction] = []
        accounts = fi_data.get("data", fi_data.get("Payload", []))
        if isinstance(accounts, dict):
            accounts = [accounts]

        for account_data in accounts:
            acc_data = account_data.get("data", account_data)
            if isinstance(acc_data, dict):
                acc_data = [acc_data]

            for entry in acc_data:
                transactions = entry.get(
                    "Transactions",
                    entry.get("transactions", {}).get("transaction", []),
                )
                if isinstance(transactions, dict):
                    transactions = transactions.get("transaction", [])

                for txn in transactions:
                    parsed = self._parse_single_txn(txn)
                    if parsed:
                        txns.append(parsed)

        return txns

    @staticmethod
    def _parse_single_txn(txn: dict) -> Transaction | None:
        txn_id = txn.get("txnId") or txn.get("id") or uuid.uuid4().hex
        raw_date = txn.get("transactionTimestamp") or txn.get("valueDate", "")
        amount_str = txn.get("amount", "0")
        narration = txn.get("narration") or txn.get("reference", "")
        txn_type = (txn.get("type") or "DEBIT").upper()

        try:
            amount = abs(float(amount_str))
        except (ValueError, TypeError):
            return None

        if not narration or amount == 0:
            return None

        # Parse date
        tx_date = raw_date[:10] if len(raw_date) >= 10 else ""
        if not tx_date:
            return None

        expense_type = "INCOME" if txn_type == "CREDIT" else "EXPENSE"

        return Transaction(
            txn_id=str(txn_id),
            date=tx_date,
            amount=amount,
            description=narration[:500],
            currency="INR",
            expense_type=expense_type,
            category_hint=None,
            meta=txn,
        )
