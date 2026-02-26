# FinMind Bank Sync — Connector Architecture

Pluggable bank integration framework for the FinMind project. Provides a
unified interface for connecting to banks, importing transactions, and
keeping data in sync.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     SyncScheduler                       │
│                  (periodic refresh)                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                     SyncEngine                          │
│          (orchestrates all connectors)                   │
│                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐ │
│  │SyncState│  │SyncState│  │SyncState│  │ SyncState │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └─────┬─────┘ │
└───────┼────────────┼────────────┼──────────────┼────────┘
        │            │            │              │
        ▼            ▼            ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   Mock   │  │  Plaid   │  │   CSV    │  │  Custom  │
│Connector │  │Connector │  │Connector │  │Connector │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
        │            │            │              │
        ▼            ▼            ▼              ▼
   [Fake Data]  [Plaid API]  [CSV Files]   [Your API]

                       │
                       ▼
         ┌───────────────────────┐
         │   Data Models         │
         │  Transaction          │
         │  Account              │
         │  Balance              │
         └───────────────────────┘
```

## Project Structure

```
finmind-bank-sync/
├── connectors/
│   ├── base.py          # Abstract BankConnector interface
│   ├── mock.py          # Mock connector (testing/demos)
│   ├── plaid.py         # Plaid API connector template
│   ├── csv_import.py    # CSV bank statement import
│   └── registry.py      # Connector registry/factory
├── models/
│   ├── transaction.py   # Transaction, Account, Balance models
│   └── sync_state.py    # Sync state tracking
├── sync/
│   ├── engine.py        # Sync orchestration engine
│   └── scheduler.py     # Periodic refresh scheduler
├── tests/
│   ├── test_models.py
│   ├── test_connectors.py
│   └── test_sync.py
├── requirements.txt
└── README.md
```

## Quick Start

```bash
pip install -r requirements.txt
```

```python
from sync.engine import SyncEngine
from datetime import datetime, timedelta

# Create engine and add a mock connector
engine = SyncEngine()
engine.add_connector("mock", connector_id="demo-bank")
engine.connect_all()

# Full import: last 30 days
results = engine.sync_all(full_import=True)
for txn in results["demo-bank"][:5]:
    print(f"  {txn.date:%Y-%m-%d}  {txn.amount:>10.2f}  {txn.description}")

# Check health
print(engine.get_health())

# Clean up
engine.disconnect_all()
```

## Connector Interface

All connectors implement `BankConnector` (see `connectors/base.py`):

| Method                              | Description                        |
|-------------------------------------|------------------------------------|
| `connect()`                         | Establish connection               |
| `disconnect()`                      | Clean up resources                 |
| `get_accounts()`                    | List connected accounts            |
| `get_balance(account_id)`           | Get account balance                |
| `import_transactions(start, end)`   | Import transactions in date range  |
| `refresh()`                         | Incremental sync since last import |

## Built-in Connectors

### MockConnector
Generates realistic fake data. Deterministic based on `connector_id`.

```python
from connectors.mock import MockConnector

conn = MockConnector(connector_id="test-1")
conn.connect()
accounts = conn.get_accounts()  # 3 accounts: checking, savings, credit
```

### CSVConnector
Import transactions from CSV bank statements.

```python
from connectors.csv_import import CSVConnector

conn = CSVConnector(config={
    "file_path": "statement.csv",
    "account_name": "Chase Checking",
    "delimiter": ",",
    "date_format": "%m/%d/%Y",  # optional, auto-detected
})
conn.connect()
txns = conn.import_transactions(start, end)
```

Supports auto-detection of date formats and currency symbols ($, €, £).

### PlaidConnector
Template for Plaid API integration. Requires `plaid-python`.

```python
from connectors.plaid import PlaidConnector

conn = PlaidConnector(config={
    "client_id": "your_client_id",
    "secret": "your_secret",
    "environment": "sandbox",
    "access_token": "access-sandbox-xxx",
})
conn.connect()
```

## Writing a Custom Connector

```python
from connectors.base import BankConnector
from connectors.registry import get_registry

class MyBankConnector(BankConnector):
    @property
    def name(self) -> str:
        return "My Bank"

    @property
    def connector_type(self) -> str:
        return "mybank"

    def connect(self):
        # your auth logic
        self._connected = True

    def disconnect(self):
        self._connected = False

    def get_accounts(self):
        self._ensure_connected()
        return [...]

    def get_balance(self, account_id):
        self._ensure_connected()
        return Balance(...)

    def import_transactions(self, start_date, end_date, account_id=None):
        self._ensure_connected()
        return [...]

    def refresh(self):
        self._ensure_connected()
        return [...]

# Register it
registry = get_registry()
registry.register("mybank", MyBankConnector)
```

## Sync Engine

The `SyncEngine` manages multiple connectors and tracks sync state:

```python
engine = SyncEngine()
engine.add_connector("mock", connector_id="bank-a")
engine.add_connector("csv", connector_id="bank-b", config={"file_path": "stmt.csv"})
engine.connect_all()

# Sync everything
results = engine.sync_all(full_import=True)

# Sync one connector
txns = engine.sync_one("bank-a")

# Monitor health
health = engine.get_health()
# {'bank-a': {'connected': True, 'status': 'success', 'healthy': True, ...}}

# Register callbacks
engine.on_sync(lambda cid, state, txns: print(f"{cid}: {len(txns)} transactions"))
```

## Scheduler

Automate periodic syncs:

```python
from sync.scheduler import SyncScheduler

scheduler = SyncScheduler(engine, default_interval=3600)  # hourly
scheduler.set_interval("bank-a", 1800)  # 30 min for this one
scheduler.start()

# Check status
print(scheduler.status())

# Stop
scheduler.stop()
```

## Running Tests

```bash
cd /tmp/finmind-bank-sync
python -m pytest tests/ -v
```

## Error Handling

The framework defines a hierarchy of exceptions:

- `ConnectorError` — base error for all connector issues
- `AuthenticationError` — invalid credentials
- `RateLimitError` — API rate limit exceeded (includes `retry_after`)
- `ConnectionError` — service unreachable

## License

MIT
