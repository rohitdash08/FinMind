"""Plaid-ready connector template using Plaid API structure."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from connectors.base import (
    AuthenticationError, BankConnector, ConnectorError, RateLimitError,
)
from models.transaction import (
    Account, AccountType, Balance, Currency, Transaction,
    TransactionStatus, TransactionType,
)

logger = logging.getLogger(__name__)

# Plaid account type mapping
_PLAID_ACCOUNT_TYPE_MAP: Dict[str, AccountType] = {
    "depository": AccountType.CHECKING,
    "credit": AccountType.CREDIT,
    "loan": AccountType.LOAN,
    "investment": AccountType.INVESTMENT,
}


class PlaidConnector(BankConnector):
    """Connector for Plaid API integration.

    Requires plaid-python SDK. Install with: pip install plaid-python

    Config keys:
        client_id: Plaid client ID
        secret: Plaid secret key
        environment: 'sandbox', 'development', or 'production'
        access_token: Plaid access token (obtained via Link flow)
    """

    def __init__(self, connector_id: str = "plaid-1", config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self._client: Any = None
        self._access_token: Optional[str] = None
        self._cursor: Optional[str] = None

    @property
    def name(self) -> str:
        return "Plaid"

    @property
    def connector_type(self) -> str:
        return "plaid"

    def connect(self) -> None:
        """Initialize Plaid client and validate access token."""
        client_id = self.config.get("client_id")
        secret = self.config.get("secret")
        environment = self.config.get("environment", "sandbox")
        self._access_token = self.config.get("access_token")

        if not all([client_id, secret, self._access_token]):
            raise AuthenticationError(
                "Plaid requires 'client_id', 'secret', and 'access_token' in config."
            )

        try:
            import plaid
            from plaid.api import plaid_api
            from plaid.model.products import Products

            env_map = {
                "sandbox": plaid.Environment.Sandbox,
                "development": plaid.Environment.Development,
                "production": plaid.Environment.Production,
            }
            configuration = plaid.Configuration(
                host=env_map.get(environment, plaid.Environment.Sandbox),
                api_key={"clientId": client_id, "secret": secret},
            )
            api_client = plaid.ApiClient(configuration)
            self._client = plaid_api.PlaidApi(api_client)
            self._connected = True
            self._logger.info("Connected to Plaid (%s environment).", environment)

        except ImportError:
            raise ConnectorError(
                "plaid-python package not installed. Run: pip install plaid-python"
            )
        except Exception as e:
            raise ConnectorError(f"Failed to initialize Plaid client: {e}")

    def disconnect(self) -> None:
        self._client = None
        self._access_token = None
        self._cursor = None
        self._connected = False
        self._logger.info("Disconnected from Plaid.")

    def get_accounts(self) -> List[Account]:
        self._ensure_connected()
        try:
            from plaid.model.accounts_get_request import AccountsGetRequest

            request = AccountsGetRequest(access_token=self._access_token)
            response = self._client.accounts_get(request)

            return [
                Account(
                    account_id=acct.account_id,
                    name=acct.name,
                    account_type=_PLAID_ACCOUNT_TYPE_MAP.get(
                        acct.type.value if hasattr(acct.type, "value") else str(acct.type),
                        AccountType.OTHER,
                    ),
                    mask=acct.mask or "",
                    official_name=acct.official_name or "",
                    institution_name="Plaid",
                    currency=Currency.USD,
                )
                for acct in response.accounts
            ]
        except Exception as e:
            raise self._handle_plaid_error(e)

    def get_balance(self, account_id: str) -> Balance:
        self._ensure_connected()
        try:
            from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest

            request = AccountsBalanceGetRequest(access_token=self._access_token)
            response = self._client.accounts_balance_get(request)

            for acct in response.accounts:
                if acct.account_id == account_id:
                    bal = acct.balances
                    return Balance(
                        account_id=account_id,
                        current=float(bal.current or 0),
                        available=float(bal.available) if bal.available else None,
                        limit=float(bal.limit) if bal.limit else None,
                    )
            raise ConnectorError(f"Account {account_id!r} not found in Plaid response.")
        except ConnectorError:
            raise
        except Exception as e:
            raise self._handle_plaid_error(e)

    def import_transactions(
        self, start_date: datetime, end_date: datetime, account_id: Optional[str] = None
    ) -> List[Transaction]:
        self._ensure_connected()
        try:
            from plaid.model.transactions_get_request import TransactionsGetRequest
            from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

            options = {}
            if account_id:
                options["account_ids"] = [account_id]

            request = TransactionsGetRequest(
                access_token=self._access_token,
                start_date=start_date.date(),
                end_date=end_date.date(),
                options=TransactionsGetRequestOptions(**options) if options else None,
            )
            response = self._client.transactions_get(request)
            return [self._map_transaction(t) for t in response.transactions]

        except Exception as e:
            raise self._handle_plaid_error(e)

    def refresh(self) -> List[Transaction]:
        """Use Plaid's transaction sync endpoint for incremental updates."""
        self._ensure_connected()
        try:
            from plaid.model.transactions_sync_request import TransactionsSyncRequest

            added: List[Transaction] = []
            has_more = True

            while has_more:
                request = TransactionsSyncRequest(
                    access_token=self._access_token,
                    cursor=self._cursor or "",
                )
                response = self._client.transactions_sync(request)
                added.extend(self._map_transaction(t) for t in response.added)
                self._cursor = response.next_cursor
                has_more = response.has_more

            return added
        except Exception as e:
            raise self._handle_plaid_error(e)

    @staticmethod
    def _map_transaction(plaid_txn: Any) -> Transaction:
        """Map a Plaid transaction object to our Transaction model."""
        amount = -float(plaid_txn.amount)  # Plaid uses positive=debit convention
        return Transaction(
            transaction_id=plaid_txn.transaction_id,
            account_id=plaid_txn.account_id,
            amount=amount,
            date=datetime.combine(plaid_txn.date, datetime.min.time()),
            description=plaid_txn.name or "",
            transaction_type=TransactionType.DEBIT if amount < 0 else TransactionType.CREDIT,
            status=TransactionStatus.PENDING if plaid_txn.pending else TransactionStatus.POSTED,
            category=", ".join(plaid_txn.category or []),
            merchant_name=plaid_txn.merchant_name or "",
            pending=plaid_txn.pending,
        )

    @staticmethod
    def _handle_plaid_error(error: Exception) -> ConnectorError:
        """Convert Plaid exceptions to ConnectorError subtypes."""
        err_str = str(error)
        if "INVALID_ACCESS_TOKEN" in err_str or "INVALID_API_KEYS" in err_str:
            return AuthenticationError(f"Plaid authentication failed: {err_str}")
        if "RATE_LIMIT" in err_str:
            return RateLimitError("Plaid rate limit exceeded")
        return ConnectorError(f"Plaid API error: {err_str}")
