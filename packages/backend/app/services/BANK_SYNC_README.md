# Bank Sync Connector Architecture

This module provides a **pluggable architecture for bank integrations** in FinMind, allowing users to connect their bank accounts and sync transactions automatically.

## Features

- 🔌 **Pluggable Connector Interface** - Easy to add new bank integrations
- 🧪 **Mock Connector Included** - Test without real bank credentials
- 🔄 **Automatic Transaction Import** - Import transactions as expenses
- 🔒 **Secure Authentication** - Token-based authentication flow
- 📊 **Health Monitoring** - Connection status and health checks

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Bank Sync Service                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Connector  │  │   Connector  │  │   Connector  │  │
│  │   (Mock)     │  │   (Plaid)    │  │   (Yodlee)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                   │                   │       │
│         └───────────────────┴───────────────────┘       │
│                           │                             │
│                    ┌──────────────┐                     │
│                    │   Registry   │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. List Available Connectors

```bash
GET /bank-sync/connectors
```

Response:
```json
[
  {"id": "mock", "name": "MockBankConnector"}
]
```

### 2. Connect to a Bank

```bash
POST /bank-sync/connect
Content-Type: application/json

{
  "connector_id": "mock",
  "credentials": {"api_key": "test_key"},
  "config": {"account_count": 3}
}
```

Response:
```json
{
  "connected": true,
  "connector_id": "mock",
  "accounts_synced": 3,
  "accounts": [
    {
      "id": "mock_acc_0",
      "name": "Checking Account 1",
      "type": "CHECKING",
      "currency": "USD",
      "balance": 5420.50,
      "account_number_masked": "****1234",
      "institution": "Mock Bank"
    }
  ]
}
```

### 3. Sync Transactions

```bash
POST /bank-sync/sync/mock_acc_0
Content-Type: application/json

{
  "connector_id": "mock",
  "credentials": {"api_key": "test_key"},
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "import_to_expenses": true
}
```

Response:
```json
{
  "success": true,
  "transactions_synced": 25,
  "transactions": [
    {
      "id": "mock_tx_abc123",
      "date": "2024-01-15",
      "amount": -45.67,
      "description": "Coffee Shop",
      "currency": "USD",
      "merchant": "Coffee Shop",
      "pending": false
    }
  ]
}
```

### 4. Check Connection Status

```bash
GET /bank-sync/status?connector_id=mock
```

Response:
```json
{
  "connector_id": "mock",
  "name": "Mock Bank",
  "authenticated": true,
  "connection_status": "ACTIVE",
  "health": {
    "status": "healthy",
    "latency_ms": 42,
    "api_version": "v1.0.0-mock"
  }
}
```

### 5. Disconnect

```bash
POST /bank-sync/disconnect
Content-Type: application/json

{
  "connector_id": "mock"
}
```

## Creating a New Bank Connector

To add support for a new bank (e.g., Plaid), implement the `BankConnector` interface:

```python
from app.services.bank_connector import BankConnector, BankAccount, BankTransaction

class PlaidConnector(BankConnector):
    def authenticate(self, credentials: dict) -> bool:
        # Implement Plaid authentication
        access_token = credentials.get("access_token")
        # ... validate token
        self._authenticated = True
        return True
    
    def fetch_accounts(self) -> list[BankAccount]:
        # Fetch accounts from Plaid API
        pass
    
    def fetch_transactions(
        self, 
        account_id: str, 
        start_date: date | None = None,
        end_date: date | None = None
    ) -> list[BankTransaction]:
        # Fetch transactions from Plaid API
        pass
    
    def refresh(self) -> bool:
        # Refresh access token
        pass
    
    def disconnect(self) -> bool:
        # Revoke access token
        pass
    
    def get_connection_status(self) -> BankConnectionStatus:
        # Return connection status
        pass
    
    def health_check(self) -> dict:
        # Return health status
        pass

# Register the connector
from app.services.bank_connector import ConnectorRegistry
ConnectorRegistry.register("plaid", PlaidConnector)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bank-sync/connectors` | List available connectors |
| POST | `/bank-sync/connect` | Connect to a bank |
| POST | `/bank-sync/sync/<account_id>` | Sync transactions |
| GET | `/bank-sync/status` | Get connection status |
| POST | `/bank-sync/disconnect` | Disconnect from bank |

## Models

### BankAccount
- `id`: Account identifier
- `name`: Account name
- `account_type`: CHECKING, SAVINGS, CREDIT_CARD
- `currency`: Currency code
- `balance`: Current balance
- `account_number_masked`: Masked account number
- `institution_name`: Bank name

### BankTransaction
- `id`: Transaction identifier
- `account_id`: Associated account
- `date`: Transaction date
- `amount`: Transaction amount (negative for expenses)
- `description`: Transaction description
- `currency`: Currency code
- `merchant_name`: Merchant name (if available)
- `pending`: Whether transaction is pending
- `metadata`: Additional metadata

### BankConnectionStatus
- `ACTIVE`: Connection is active
- `EXPIRED`: Token expired, needs refresh
- `ERROR`: Connection error
- `DISCONNECTED`: Not connected

## Testing

Run tests with:

```bash
# Using Docker (recommended)
./scripts/test-backend.sh tests/test_bank_sync.py

# Or manually
cd packages/backend
python -m pytest tests/test_bank_sync.py -v
```

## Configuration

Add configuration to your `.env` file:

```env
# Bank sync settings
BANK_SYNC_ENABLED=true
BANK_SYNC_MAX_TRANSACTIONS=1000
BANK_SYNC_DEFAULT_DAYS=90
```

## Bounty Information

- **Issue**: rohitdash08/FinMind#75
- **Bounty**: $500
- **Deliverables**:
  - ✅ Connector interface
  - ✅ Import & refresh support
  - ✅ Mock connector included

## License

MIT License - Same as FinMind project
