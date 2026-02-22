# Bank Sync Connector Architecture

## Overview

FinMind uses a pluggable connector architecture for bank integrations. Each bank provider (Plaid, Teller, etc.) implements the `BankConnector` interface, enabling standardized import and refresh flows.

## Adding a New Provider

1. Create a new file in `app/services/` (e.g., `bank_plaid.py`)
2. Implement the `BankConnector` abstract class
3. Register with `@ConnectorRegistry.register`

```python
from .bank_connector import BankConnector, ConnectorRegistry, BankAccountInfo, BankTransactionData

@ConnectorRegistry.register
class PlaidConnector(BankConnector):
    @property
    def provider_name(self) -> str:
        return "plaid"

    def authenticate(self, credentials: dict) -> dict:
        # Exchange public token for access token
        access_token = plaid_client.exchange(credentials["public_token"])
        return {"access_token": access_token}

    def list_accounts(self, connection_data: dict) -> list[BankAccountInfo]:
        # Fetch accounts from Plaid API
        ...

    def fetch_transactions(self, connection_data, account_id, from_date, to_date):
        # Fetch transactions from Plaid API
        ...

    def refresh_connection(self, connection_data: dict) -> dict:
        # Refresh access token if needed
        ...
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bank/providers` | List available providers |
| POST | `/bank/connect` | Create new connection |
| GET | `/bank/connections` | List user's connections |
| GET | `/bank/connections/:id/accounts` | List available accounts |
| POST | `/bank/connections/:id/sync` | Import transactions |
| POST | `/bank/connections/:id/refresh` | Refresh connection |
| GET | `/bank/connections/:id/transactions` | View imported transactions |
| DELETE | `/bank/connections/:id` | Remove connection |

## Mock Connector

A `MockBankConnector` is included for testing. It generates deterministic sample data without requiring real bank credentials.

```python
# Connect with mock provider
POST /bank/connect
{
    "provider": "mock",
    "credentials": {"username": "demo"}
}
```
