"""
Bank Sync Connector Architecture
A pluggable architecture for bank integrations supporting import and refresh operations.
"""

import abc
import json
import logging
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Type, Union, ClassVar
from pathlib import Path
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class AccountType(Enum):
    """Enumeration of account types."""
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"
    LOAN = "loan"
    MORTGAGE = "mortgage"
    OTHER = "other"


class TransactionType(Enum):
    """Enumeration of transaction types."""
    DEBIT = "debit"
    CREDIT = "credit"
    TRANSFER = "transfer"
    FEE = "fee"
    INTEREST = "interest"
    OTHER = "other"


@dataclass
class Account:
    """Data model for bank account information."""
    
    account_id: str
    account_number: str
    account_name: str
    account_type: AccountType
    currency: str = "USD"
    balance: float = 0.0
    available_balance: float = 0.0
    institution_name: Optional[str] = None
    owner_name: Optional[str] = None
    opened_date: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert account to dictionary."""
        data = asdict(self)
        data['account_type'] = self.account_type.value
        data['opened_date'] = self.opened_date.isoformat() if self.opened_date else None
        data['last_updated'] = self.last_updated.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Account':
        """Create account from dictionary."""
        data = data.copy()
        data['account_type'] = AccountType(data['account_type'])
        if data.get('opened_date'):
            data['opened_date'] = datetime.fromisoformat(data['opened_date'])
        if data.get('last_updated'):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


@dataclass
class Transaction:
    """Data model for bank transaction information."""
    
    transaction_id: str
    account_id: str
    amount: float
    currency: str = "USD"
    transaction_type: TransactionType = TransactionType.OTHER
    description: str = ""
    merchant_name: Optional[str] = None
    merchant_category: Optional[str] = None
    transaction_date: datetime = field(default_factory=datetime.now)
    posted_date: Optional[datetime] = None
    reference_number: Optional[str] = None
    status: str = "completed"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to dictionary."""
        data = asdict(self)
        data['transaction_type'] = self.transaction_type.value
        data['transaction_date'] = self.transaction_date.isoformat()
        data['posted_date'] = self.posted_date.isoformat() if self.posted_date else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create transaction from dictionary."""
        data = data.copy()
        data['transaction_type'] = TransactionType(data['transaction_type'])
        data['transaction_date'] = datetime.fromisoformat(data['transaction_date'])
        if data.get('posted_date'):
            data['posted_date'] = datetime.fromisoformat(data['posted_date'])
        return cls(**data)


@dataclass
class Balance:
    """Data model for account balance information."""
    
    account_id: str
    balance: float
    available_balance: float
    currency: str = "USD"
    as_of_date: datetime = field(default_factory=datetime.now)
    pending_transactions: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert balance to dictionary."""
        data = asdict(self)
        data['as_of_date'] = self.as_of_date.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Balance':
        """Create balance from dictionary."""
        data = data.copy()
        data['as_of_date'] = datetime.fromisoformat(data['as_of_date'])
        return cls(**data)


# ============================================================================
# Configuration Management
# ============================================================================

@dataclass
class ConnectorConfig:
    """Configuration for a bank connector."""
    
    connector_type: str
    name: str
    enabled: bool = True
    credentials: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    sync_settings: Dict[str, Any] = field(default_factory=lambda: {
        "sync_frequency": "daily",
        "transaction_days": 90,
        "include_pending": True
    })
    
    def validate(self) -> bool:
        """Validate configuration."""
        if not self.connector_type:
            raise ValueError("connector_type is required")
        if not self.name:
            raise ValueError("name is required")
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectorConfig':
        """Create config from dictionary."""
        return cls(**data)


class ConfigLoader:
    """Configuration loader supporting YAML and JSON formats."""
    
    @staticmethod
    def load(file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from file."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix.lower() in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            elif file_path.suffix.lower() == '.json':
                return json.load(f)
            else:
                raise ValueError(f"Unsupported config file format: {file_path.suffix}")
    
    @staticmethod
    def save(data: Dict[str, Any], file_path: Union[str, Path]) -> None:
        """Save configuration to file."""
        file_path = Path(file_path)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            if file_path.suffix.lower() in ['.yaml', '.yml']:
                yaml.dump(data, f, default_flow_style=False)
            elif file_path.suffix.lower() == '.json':
                json.dump(data, f, indent=2)
            else:
                raise ValueError(f"Unsupported config file format: {file_path.suffix}")


# ============================================================================
# Bank Connector Interface
# ============================================================================

class BankConnector(ABC):
    """
    Abstract base class for all bank connectors.
    All bank integrations must implement this interface.
    """
    
    def __init__(self, config: ConnectorConfig):
        """
        Initialize the connector with configuration.
        
        Args:
            config: Connector configuration
        """
        self.config = config
        self._connected = False
        self._last_sync: Optional[datetime] = None
        logger.info(f"Initialized {self.__class__.__name__} connector: {config.name}")
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the bank.
        
        Returns:
            bool: True if connection successful, False otherwise
        
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the bank.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def sync_accounts(self) -> List[Account]:
        """
        Synchronize account information from the bank.
        
        Returns:
            List[Account]: List of synchronized accounts
        
        Raises:
            SyncError: If synchronization fails
        """
        pass
    
    @abstractmethod
    def sync_transactions(
        self, 
        account_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """
        Synchronize transactions for a specific account.
        
        Args:
            account_id: Account identifier
            start_date: Start date for transaction range (default: 90 days ago)
            end_date: End date for transaction range (default: now)
        
        Returns:
            List[Transaction]: List of synchronized transactions
        
        Raises:
            SyncError: If synchronization fails
            ValueError: If account_id is invalid
        """
        pass
    
    @abstractmethod
    def refresh_transactions(
        self, 
        account_id: str, 
        last_refresh: Optional[datetime] = None
    ) -> List[Transaction]:
        """
        Refresh transactions since last synchronization.
        
        Args:
            account_id: Account identifier
            last_refresh: Last refresh timestamp (default: last sync time)
        
        Returns:
            List[Transaction]: List of new/updated transactions
        
        Raises:
            SyncError: If refresh fails
            ValueError: If account_id is invalid
        """
        pass
    
    @abstractmethod
    def get_balance(self, account_id: str) -> Balance:
        """
        Get current balance for an account.
        
        Args:
            account_id: Account identifier
        
        Returns:
            Balance: Current balance information
        
        Raises:
            SyncError: If balance retrieval fails
            ValueError: If account_id is invalid
        """
        pass
    
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._connected
    
    def get_last_sync(self) -> Optional[datetime]:
        """Get last synchronization timestamp."""
        return self._last_sync
    
    def update_last_sync(self) -> None:
        """Update last synchronization timestamp."""
        self._last_sync = datetime.now()
    
    def validate_credentials(self) -> bool:
        """
        Validate connector credentials.
        
        Returns:
            bool: True if credentials are valid
        
        Raises:
            ValueError: If credentials are invalid
        """
        if not self.config.credentials:
            raise ValueError("No credentials provided")
        return True


# ============================================================================
# Connector Manager
# ============================================================================

class ConnectorManager:
    """
    Manager for registering, creating, and managing bank connectors.
    """
    
    _connector_registry: ClassVar[Dict[str, Type[BankConnector]]] = {}
    
    def __init__(self):
        """Initialize connector manager."""
        self._connectors: Dict[str, BankConnector] = {}
        self._configs: Dict[str, ConnectorConfig] = {}
        logger.info("Initialized ConnectorManager")
    
    @classmethod
    def register_connector(cls, connector_type: str, connector_class: Type[BankConnector]) -> None:
        """
        Register a connector class.
        
        Args:
            connector_type: Unique identifier for connector type
            connector_class: Connector class to register
        
        Raises:
            ValueError: If connector_type is already registered
        """
        if connector_type in cls._connector_registry:
            raise ValueError(f"Connector type '{connector_type}' already registered")
        
        if not issubclass(connector_class, BankConnector):
            raise ValueError(f"Connector class must inherit from BankConnector")
        
        cls._connector_registry[connector_type] = connector_class
        logger.info(f"Registered connector type: {connector_type}")
    
    @classmethod
    def get_registered_connectors(cls) -> Dict[str, Type[BankConnector]]:
        """Get all registered connector types."""
        return cls._connector_registry.copy()
    
    def create_connector(self, config: ConnectorConfig) -> BankConnector:
        """
        Create a connector instance from configuration.
        
        Args:
            config: Connector configuration
        
        Returns:
            BankConnector: Created connector instance
        
        Raises:
            ValueError: If connector type is not registered or config is invalid
        """
        # Validate configuration
        config.validate()
        
        # Check if connector type is registered
        if config.connector_type not in self._connector_registry:
            raise ValueError(f"Unknown connector type: {config.connector_type}")
        
        # Create connector instance
        connector_class = self._connector_registry[config.connector_type]
        connector = connector_class(config)
        
        # Store connector and config
        self._connectors[config.name] = connector
        self._configs[config.name] = config
        
        logger.info(f"Created connector: {config.name} ({config.connector_type})")
        return connector
    
    def get_connector(self, name: str) -> Optional[BankConnector]:
        """Get connector by name."""
        return self._connectors.get(name)
    
    def get_all_connectors(self) -> Dict[str, BankConnector]:
        """Get all created connectors."""
        return self._connectors.copy()
    
    def remove_connector(self, name: str) -> bool:
        """
        Remove a connector.
        
        Args:
            name: Connector name
        
        Returns:
            bool: True if connector was removed, False if not found
        """
        if name in self._connectors:
            connector = self._connectors[name]
            if connector.is_connected():
                connector.disconnect()
            
            del self._connectors[name]
            del self._configs[name]
            
            logger.info(f"Removed connector: {name}")
            return True
        
        return False
    
    def connect_all(self) -> Dict[str, bool]:
        """
        Connect all enabled connectors.
        
        Returns:
            Dict[str, bool]: Mapping of connector names to connection status
        """
        results = {}
        
        for name, connector in self._connectors.items():
            config = self._configs[name]
            
            if not config.enabled:
                logger.info(f"Skipping disabled connector: {name}")
                results[name] = False
                continue
            
            try:
                success = connector.connect()
                results[name] = success
                
                if success:
                    logger.info(f"Connected connector: {name}")
                else:
                    logger.error(f"Failed to connect connector: {name}")
            
            except Exception as e:
                logger.error(f"Error connecting connector {name}: {str(e)}")
                results[name] = False
        
        return results
    
    def disconnect_all(self) -> Dict[str, bool]:
        """
        Disconnect all connectors.
        
        Returns:
            Dict[str, bool]: Mapping of connector names to disconnection status
        """
        results = {}
        
        for name, connector in self._connectors.items():
            try:
                success = connector.disconnect()
                results[name] = success
                
                if success:
                    logger.info(f"Disconnected connector: {name}")
                else:
                    logger.warning(f"Failed to disconnect connector: {name}")
            
            except Exception as e:
                logger.error(f"Error disconnecting connector {name}: {str(e)}")
                results[name] = False
        
        return results
    
    def sync_all_accounts(self) -> Dict[str, List[Account]]:
        """
        Synchronize accounts from all connectors.
        
        Returns:
            Dict[str, List[Account]]: Mapping of connector names to synchronized accounts
        """
        results = {}
        
        for name, connector in self._connectors.items():
            if not connector.is_connected():
                logger.warning(f"Skipping disconnected connector: {name}")
                continue
            
            try:
                accounts = connector.sync_accounts()
                connector.update_last_sync()
                results[name] = accounts
                
                logger.info(f"Synced {len(accounts)} accounts from connector: {name}")
            
            except Exception as e:
                logger.error(f"Error syncing accounts from connector {name}: {str(e)}")
                results[name] = []
        
        return results


# ============================================================================
# Mock Connector Implementation
# ============================================================================

class MockConnector(BankConnector):
    """
    Mock connector for testing and reference implementation.
    Generates synthetic account and transaction data.
    """
    
    def __init__(self, config: ConnectorConfig):
        """Initialize mock connector."""
        super().__init__(config)
        self._accounts: Dict[str, Account] = {}
        self._transactions: Dict[str, List[Transaction]] = {}
        self._initialize_mock_data()
    
    def _initialize_mock_data(self) -> None:
        """Initialize mock data for testing."""
        # Create mock accounts
        account_types = [
            (AccountType.CHECKING, "1234567890", "Primary Checking"),
            (AccountType.SAVINGS, "0987654321", "Savings Account"),
            (AccountType.CREDIT_CARD, "5555666677778888", "Credit Card"),
            (AccountType.INVESTMENT, "INV001", "Investment Account"),
        ]
        
        for i, (acc_type, acc_num, acc_name) in enumerate(account_types):
            account_id = f"MOCK_ACC_{i+1:03d}"
            account = Account(
                account_id=account_id,
                account_number=acc_num,
                account_name=acc_name,
                account_type=acc_type,
                currency="USD",
                balance=10000.0 * (i + 1),
                available_balance=9500.0 * (i + 1),
                institution_name="Mock Bank",
                owner_name="John Doe",
                opened_date=datetime.now() - timedelta(days=365 * 2),
                last_updated=datetime.now()
            )
            self._accounts[account_id] = account
        
        # Create mock transactions for each account
        transaction_types = [
            TransactionType.DEBIT,
            TransactionType.CREDIT,
            TransactionType.TRANSFER,
            TransactionType.FEE,
            TransactionType.INTEREST,
        ]
        
        merchants = [
            "Amazon",
            "Starbucks",
            "Walmart",
            "Netflix",
            "Uber",
            "Apple",
            "Google",
            "Target",
            "Whole Foods",
            "Costco",
        ]
        
        for account_id in self._accounts.keys():
            transactions = []
            
            # Generate transactions for the last 90 days
            for i in range(50):
                days_ago = i * 2  # Spread transactions over time
                transaction_date = datetime.now() - timedelta(days=days_ago)
                
                transaction = Transaction(
                    transaction_id=f"MOCK_TXN_{account_id}_{i:06d}",
                    account_id=account_id,
                    amount=(-50.0 if i % 3 == 0 else 100.0) * (i % 5 + 1),
                    currency="USD",
                    transaction_type=transaction_types[i % len(transaction_types)],
                    description=f"Mock transaction {i}",
                    merchant_name=merchants[i % len(merchants)],
                    merchant_category=["Shopping", "Food", "Entertainment", "Transport"][i % 4],
                    transaction_date=transaction_date,
                    posted_date=transaction_date + timedelta(hours=2),
                    reference_number=f"REF{transaction_date.strftime('%Y%m%d')}{i:04d}",
                    status="completed"
                )
                transactions.append(transaction)
            
            self._transactions[account_id] = transactions
    
    def connect(self) -> bool:
        """Mock connection always succeeds."""
        logger.info(f"Mock connector connecting: {self.config.name}")
        self._connected = True
        return True
    
    def disconnect(self) -> bool:
        """Mock disconnection always succeeds."""
        logger.info(f"Mock connector disconnecting: {self.config.name}")
        self._connected = False
        return True
    
    def sync_accounts(self) -> List[Account]:
        """Return mock accounts."""
        if not self._connected:
            raise ConnectionError("Mock connector not connected")
        
        accounts = list(self._accounts.values())
        
        # Update last updated timestamp
        for account in accounts:
            account.last_updated = datetime.now()
        
        logger.info(f"Mock connector synced {len(accounts)} accounts")
        return accounts
    
    def sync_transactions(
        self, 
        account_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """Return mock transactions for account within date range."""
        if not self._connected:
            raise ConnectionError("Mock connector not connected")
        
        if account_id not in self._transactions:
            raise ValueError(f"Account not found: {account_id}")
        
        # Set default date range if not provided
        if start_date is None:
            start_date = datetime.now() - timedelta(days=90)
        if end_date is None:
            end_date = datetime.now()
        
        # Filter transactions by date range
        transactions = self._transactions[account_id]
        filtered_transactions = [
            txn for txn in transactions
            if start_date <= txn.transaction_date <= end_date
        ]
        
        logger.info(f"Mock connector synced {len(filtered_transactions)} transactions for account {account_id}")
        return filtered_transactions
    
    def refresh_transactions(
        self, 
        account_id: str, 
        last_refresh: Optional[datetime] = None
    ) -> List[Transaction]:
        """Return new mock transactions since last refresh."""
        if not self._connected:
            raise ConnectionError("Mock connector not connected")
        
        if account_id not in self._transactions:
            raise ValueError(f"Account not found: {account_id}")
        
        # Set default last refresh if not provided
        if last_refresh is None:
            last_refresh = self._last_sync or (datetime.now() - timedelta(days=1))
        
        # Filter transactions since last refresh
        transactions = self._transactions[account_id]
        new_transactions = [
            txn for txn in transactions
            if txn.transaction_date > last_refresh
        ]
        
        # Generate some new mock transactions
        if not new_transactions:
            # Create a few new transactions
            for i in range(3):
                transaction = Transaction(
                    transaction_id=f"MOCK_NEW_{account_id}_{uuid.uuid4().hex[:8]}",
                    account_id=account_id,
                    amount=(-25.0 if i % 2 == 0 else 75.0),
                    currency="USD",
                    transaction_type=TransactionType.DEBIT if i % 2 == 0 else TransactionType.CREDIT,
                    description=f"New mock transaction {i}",
                    merchant_name=["Amazon", "Starbucks", "Uber"][i],
                    transaction_date=datetime.now() - timedelta(hours=i * 6),
                    posted_date=datetime.now() - timedelta(hours=i * 5),
                    status="completed"
                )
                new_transactions.append(transaction)
        
        logger.info(f"Mock connector refreshed {len(new_transactions)} transactions for account {account_id}")
        return new_transactions
    
    def get_balance(self, account_id: str) -> Balance:
        """Return mock balance for account."""
        if not self._connected:
            raise ConnectionError("Mock connector not connected")
        
        if account_id not in self._accounts:
            raise ValueError(f"Account not found: {account_id}")
        
        account = self._accounts[account_id]
        
        # Simulate some pending transactions
        pending_transactions = [
            {"id": "PEND001", "amount": -50.0, "description": "Pending purchase"},
            {"id": "PEND002", "amount": 100.0, "description": "Pending deposit"},
        ]
        
        balance = Balance(
            account_id=account_id,
            balance=account.balance,
            available_balance=account.available_balance,
            currency=account.currency,
            as_of_date=datetime.now(),
            pending_transactions=pending_transactions
        )
        
        logger.info(f"Mock connector retrieved balance for account {account_id}")
        return balance


# ============================================================================
# Custom Exceptions
# ============================================================================

class BankConnectorError(Exception):
    """Base exception for bank connector errors."""
    pass


class ConnectionError(BankConnectorError):
    """Exception raised when connection fails."""
    pass


class SyncError(BankConnectorError):
    """Exception raised when synchronization fails."""
    pass


class ConfigurationError(BankConnectorError):
    """Exception raised when configuration is invalid."""
    pass


# ============================================================================
# Example Usage and Demonstration
# ============================================================================

def create_example_config() -> Dict[str, Any]:
    """Create example configuration."""
    return {
        "connectors": [
            {
                "connector_type": "mock",
                "name": "mock_bank_1",
                "enabled": True,
                "credentials": {
                    "api_key": "mock_key_123",
                    "environment": "sandbox"
                },
                "parameters": {
                    "max_retries": 3,
                    "timeout": 30
                },
                "sync_settings": {
                    "sync_frequency": "daily",
                    "transaction_days": 90,
                    "include_pending": True
                }
            },
            {
                "connector_type": "mock",
                "name": "mock_bank_2",
                "enabled": True,
                "credentials": {
                    "api_key": "mock_key_456",
                    "environment": "sandbox"
                },
                "sync_settings": {
                    "sync_frequency": "hourly",
                    "transaction_days": 30,
                    "include_pending": False
                }
            }
        ]
    }


def main():
    """Demonstrate the bank connector architecture."""
    print("=" * 60)
    print("Bank Sync Connector Architecture Demo")
    print("=" * 60)
    
    # Register the mock connector
    ConnectorManager.register_connector("mock", MockConnector)
    
    # Create connector manager
    manager = ConnectorManager()
    
    # Create example configuration
    config_data = create_example_config()
    
    # Create connectors from configuration
    print("\n1. Creating connectors from configuration...")
    for connector_config in config_data["connectors"]:
        config = ConnectorConfig.from_dict(connector_config)
        try:
            connector = manager.create_connector(config)
            print(f"   Created connector: {config.name} ({config.connector_type})")
        except Exception as e:
            print(f"   Error creating connector {config.name}: {str(e)}")
    
    # Connect all connectors
    print("\n2. Connecting all connectors...")
    connection_results = manager.connect_all()
    for name, success in connection_results.items():
        status = "✓ Connected" if success else "✗ Failed"
        print(f"   {name}: {status}")
    
    # Sync accounts from all connectors
    print("\n3. Synchronizing accounts...")
    sync_results = manager.sync_all_accounts()
    for name, accounts in sync_results.items():
        print(f"   {name}: Synced {len(accounts)} accounts")
        
        # Display first account details
        if accounts:
            first_account = accounts[0]
            print(f"     Example account: {first_account.account_name} "
                  f"({first_account.account_type.value}) - "
                  f"Balance: ${first_account.balance:.2f}")
    
    # Get specific connector and sync transactions
    print("\n4. Synchronizing transactions for specific account...")
    mock_connector = manager.get_connector("mock_bank_1")
    
    if mock_connector and mock_connector.is_connected():
        accounts = mock_connector.sync_accounts()
        
        if accounts:
            account_id = accounts[0].account_id
            
            # Sync transactions for last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            transactions = mock_connector.sync_transactions(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date
            )
            
            print(f"   Synced {len(transactions)} transactions for account {account_id}")
            
            # Display first few transactions
            if transactions:
                print("   Recent transactions:")
                for txn in transactions[:3]:
                    sign = "-" if txn.amount < 0 else "+"
                    print(f"     {txn.transaction_date.strftime('%Y-%m-%d')}: "
                          f"{txn.merchant_name or txn.description} - "
                          f"{sign}${abs(txn.amount):.2f}")
    
    # Refresh transactions
    print("\n5. Refreshing transactions...")
    if mock_connector and mock_connector.is_connected() and accounts:
        new_transactions = mock_connector.refresh_transactions(
            account_id=account_id,
            last_refresh=datetime.now() - timedelta(days=1)
        )
        print(f"   Refreshed {len(new_transactions)} new transactions")
    
    # Get account balance
    print("\n6. Getting account balance...")
    if mock_connector and mock_connector.is_connected() and accounts:
        balance = mock_connector.get_balance(account_id)
        print(f"   Account {account_id}:")
        print(f"     Current balance: ${balance.balance:.2f}")
        print(f"     Available balance: ${balance.available_balance:.2f}")
        print(f"     Pending transactions: {len(balance.pending_transactions)}")
    
    # Disconnect all connectors
    print("\n7. Disconnecting all connectors...")
    disconnect_results = manager.disconnect_all()
    for name, success in disconnect_results.items():
        status = "✓ Disconnected" if success else "✗ Failed"
        print(f"   {name}: {status}")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()