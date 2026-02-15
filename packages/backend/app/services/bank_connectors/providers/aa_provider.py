from __future__ import annotations

import os
from typing import Any

import requests

from ..base import BankConnector


class AAProviderConnector(BankConnector):
    provider_id = "aa_provider"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._connected = False
        self._configured = False
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None

    def connect(self, config: dict) -> None:
        self._base_url = config.get("base_url") or os.getenv("AA_PROVIDER_BASE_URL")
        self._api_key = config.get("api_key") or os.getenv("AA_PROVIDER_API_KEY")
        self._client_id = config.get("client_id") or os.getenv("AA_PROVIDER_CLIENT_ID")
        self._client_secret = config.get("client_secret") or os.getenv(
            "AA_PROVIDER_CLIENT_SECRET"
        )

        self._configured = all(
            [self._base_url, self._api_key, self._client_id, self._client_secret]
        )
        if not self._configured:
            self._connected = True
            return

        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._api_key}",
                "X-Client-Id": self._client_id,
                "X-Client-Secret": self._client_secret,
                "Content-Type": "application/json",
            }
        )
        self._connected = True

    def import_accounts(self) -> list:
        self._ensure_connected()
        if not self._configured:
            return []

        # Placeholder: swap endpoint/path for provider partner portal implementation.
        response = self._session.get(f"{self._base_url}/accounts", timeout=15)
        if response.status_code >= 400:
            response.raise_for_status()

        payload: dict[str, Any] = response.json() if response.content else {}
        accounts = payload.get("accounts", [])
        return accounts if isinstance(accounts, list) else []

    def import_transactions(self, cursor=None) -> tuple[list, str | None]:
        self._ensure_connected()
        if not self._configured:
            return [], None

        params = {"cursor": cursor} if cursor else {}

        # Placeholder: swap endpoint/path and mapping for AA/API provider format.
        response = self._session.get(
            f"{self._base_url}/transactions", params=params, timeout=20
        )
        if response.status_code >= 400:
            response.raise_for_status()

        payload: dict[str, Any] = response.json() if response.content else {}
        transactions = payload.get("transactions", [])
        next_cursor = payload.get("next_cursor")

        if not isinstance(transactions, list):
            transactions = []
        if next_cursor is not None and not isinstance(next_cursor, str):
            next_cursor = None

        return transactions, next_cursor

    def refresh(self, cursor=None) -> tuple[list, str | None]:
        self._ensure_connected()
        return self.import_transactions(cursor=cursor)

    def disconnect(self) -> None:
        self._connected = False

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("AAProviderConnector is not connected")
