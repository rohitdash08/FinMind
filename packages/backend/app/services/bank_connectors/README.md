# Bank Connectors Architecture

Pluggable architecture for bank integrations in FinMind.

## Overview

This module provides a flexible, extensible system for connecting to banks and financial institutions to import transactions and account data.

## Components

### 1. Base Interface (`base.py`)

- **`BaseBankConnector`**: Abstract base class for all connectors
- **`BankConnector`**: Protocol interface for type checking
- **`TokenInfo`**: OAuth token information dataclass
- **`Account`**: Bank account information dataclass
- **`Transaction`**: Bank transaction dataclass
- **`ConnectorConfig`**: Configuration for connectors

### 2. Factory (`factory.py`)

- **`get_connector(institution_id)`**: Get a connector instance by ID
- **`register_connector`**: Decorator to register new connectors
- **`list_available_connectors()`**: List all available connectors

### 3. Mock Connector (`mock_connector.py`)

- **`MockBankConnector`**: Test/dummy connector for development

## Usage

### Listing Available Connectors

```python
from app.services.bank_connectors import list_available_connectors

connectors = list_available_connectors()
# Returns: [{'institution_id': 'mock_bank', 'institution_name': 'Mock Bank (Test)', ...}]
```

### Getting a Connector

```python
from app.services.bank_connectors import get_connector

connector = get_connector("mock_bank")
```

### Creating a Custom Connector

```python
from app.services.bank_connectors import (
    BaseBankConnector,
    TokenInfo,
    Account,
    Transaction,
    register_connector,
)
from datetime import date

@register_connector
class MyBankConnector(BaseBankConnector):
    @property
    def institution_id(self) -> str:
        return "my_bank"
    
    @property
    def institution_name(self) -> str:
        return "My Bank"
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        # Return OAuth URL
        return f"https://mybank.com/oauth?redirect={redirect_uri}&state={state}"
    
    def exchange_code(self, code: str, redirect_uri: str) -> TokenInfo:
        # Exchange code for tokens
        return TokenInfo(access_token="...", refresh_token="...")
    
    def refresh_token(self, token_info: TokenInfo) -> TokenInfo:
        # Refresh expired token
        return TokenInfo(access_token="...")
    
    def get_accounts(self, token_info: TokenInfo) -> list[Account]:
        # Fetch accounts
        return [Account(account_id="...", account_name="...")]
    
    def get_transactions(self, token_info, account_id, start_date, end_date):
        # Fetch transactions
        return [Transaction(transaction_id="...", amount=...)]
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bank/connectors` | List available connectors |
| GET | `/bank/connectors/<id>/authorization_url` | Get OAuth URL |
| POST | `/bank/connectors/<id>/exchange` | Exchange OAuth code |
| POST | `/bank/connectors/<id>/refresh` | Refresh token |
| GET | `/bank/connectors/<id>/accounts` | Get accounts |
| GET | `/bank/connectors/<id>/transactions` | Get transactions |
| POST | `/bank/connectors/<id>/disconnect` | Disconnect |
| POST | `/bank/import/transactions` | Import to expenses |

## Acceptance Criteria Met

✅ **Connector Interface**: Abstract base class with concrete implementations  
✅ **Import Support**: `/bank/import/transactions` endpoint imports transactions as expenses  
✅ **Refresh Support**: Token refresh flow with `/bank/connectors/<id>/refresh`  
✅ **Mock Connector**: `MockBankConnector` included for testing  
✅ **Tests**: 19 tests covering all components