# Bank Connectors Guide

Complete guide for implementing and using bank connectors in FinMind.

## Available Connectors

### 1. Mock Bank (Development)
- **ID:** `mock_bank`
- **Type:** Development/Testing
- **Features:** All features simulated
- **Setup:** Zero configuration required

### 2. Plaid (Production)
- **ID:** `plaid`
- **Type:** Production
- **Features:** Real bank connections via Plaid
- **Coverage:** 12,000+ financial institutions
- **Setup:** Requires Plaid account + API keys

## Quick Start

### Using Mock Connector (No Setup)

```python
from app.connectors import get_connector

# Get mock connector
connector = get_connector('mock_bank')

# Connect with test credentials
from app.connectors.base import ConnectionCredentials

creds = ConnectionCredentials(
    additional_data={'username': 'test', '***word': '***'}
)
result = connector.connect(creds)

# Use the connection
creds.access_token = result['access_token']
accounts = connector.get_accounts(creds)
```

### Using Plaid Connector (Production)

```python
import os

# Set credentials
os.environ['PLAID_CLIENT_ID'] = 'your-client-id'
os.environ['PLAID_SECRET'] = 'your-secret'

# Get connector with config
connector = get_connector('plaid')

# Connect via Plaid Link (frontend required)
# After frontend exchange, use public_token
creds = ConnectionCredentials(
    additional_data={'public_token': 'public-token-from-link'}
)
result = connector.connect(creds)
```

## Connector Interface

All connectors implement these 8 methods:

```python
class BankConnector:
    # Establish connection
    def connect(credentials) -> dict
    
    # Validate token is still valid
    def validate_credentials(credentials) -> bool
    
    # Refresh expired token
    def refresh_connection(credentials) -> credentials
    
    # Get all accounts
    def get_accounts(credentials) -> list[BankAccount]
    
    # Get transactions for an account
    def get_transactions(credentials, account_id, start_date, end_date) -> list[Transaction]
    
    # Get current balance
    def get_balance(credentials, account_id) -> BankAccount
    
    # Revoke connection
    def disconnect(credentials) -> bool
    
    # Check connection health
    def get_connection_status(credentials) -> ConnectionStatus
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bank-sync/connectors` | List all connectors |
| POST | `/bank-sync/connections` | Create new connection |
| GET | `/bank-sync/connections` | List user connections |
| GET | `/bank-sync/connections/{id}` | Get connection details |
| DELETE | `/bank-sync/connections/{id}` | Delete connection |
| POST | `/bank-sync/connections/{id}/sync` | Sync transactions |
| GET | `/bank-sync/connections/{id}/accounts` | List accounts |
| GET | `/bank-sync/accounts/{id}/transactions` | Get transactions |

## Testing

```bash
# Run all connector tests
pytest tests/test_bank_sync.py -v

# Test specific connector
pytest tests/test_bank_sync.py -k "MockConnector" -v
```

## Adding a New Connector

1. Create file in `app/connectors/your_connector.py`
2. Extend `BankConnector` base class
3. Implement all 8 abstract methods
4. Register in `app/connectors/__init__.py`

### Example Structure:

```python
from .base import BankConnector, ConnectionCredentials, BankAccount, Transaction

class YourConnector(BankConnector):
    name = "your_bank"
    display_name = "Your Bank"
    description = "Connect to Your Bank"
    supported_countries = ["US"]
    features = ["transactions", "balance"]
    
    def connect(self, credentials: ConnectionCredentials):
        # Implement connection logic
        pass
    
    # ... implement other 7 methods
```

## Data Models

### BankAccount
```python
{
    "id": "account-id",
    "name": "Checking Account",
    "account_type": "checking",
    "currency": "USD",
    "balance": 1250.00,
    "masked_number": "****4242"
}
```

### Transaction
```python
{
    "id": "transaction-id",
    "account_id": "account-id",
    "amount": -45.50,
    "currency": "USD",
    "description": "Starbucks Purchase",
    "merchant_name": "Starbucks",
    "transaction_date": "2026-06-02",
    "pending": false
}
```

## Security Best Practices

1. **Never log access tokens**
2. **Always use HTTPS**
3. **Store tokens encrypted at rest**
4. **Implement token refresh before expiry**
5. **Disconnect gracefully on errors**

## Troubleshooting

### Mock Connector Issues
- Check credentials format: `{username, password}`
- Password `***` triggers failure simulation

### Plaid Integration Issues
- Verify `PLAID_CLIENT_ID` and `PLAID_SECRET` are set
- Check environment (sandbox/development/production)
- Ensure `plaid-python` is installed
- Check country support for target institution

## Environment Variables

```bash
# Plaid Configuration
PLAID_CLIENT_ID=your-client-id
PLAID_SECRET=your-secret
PLAID_ENV=sandbox  # or development, production

# Database (for storing connections)
DATABASE_URL=postgresql://user:pass@localhost/finmind
```

---

**Ready to integrate?** Start with the mock connector for development, then switch to Plaid for production!
