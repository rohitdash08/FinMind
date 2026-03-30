"""
Tests for bank connectors architecture
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.bank_connectors.base import (
    BaseBankConnector,
    ConnectorConfig,
    TokenInfo,
    Account,
    Transaction,
    ConnectorStatus,
)
from app.services.bank_connectors.factory import (
    get_connector,
    register_connector,
    list_available_connectors,
    clear_registry,
)
from app.services.bank_connectors import MockBankConnector


class TestTokenInfo:
    """Tests for TokenInfo dataclass"""
    
    def test_token_info_creation(self):
        token = TokenInfo(
            access_token="test_access",
            refresh_token="test_refresh",
        )
        assert token.access_token == "test_access"
        assert token.refresh_token == "test_refresh"
        assert token.token_type == "Bearer"
    
    def test_is_expired_no_expiry(self):
        token = TokenInfo(access_token="test")
        assert not token.is_expired()
    
    def test_is_expired_with_future_expiry(self):
        token = TokenInfo(
            access_token="test",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert not token.is_expired()
    
    def test_is_expired_with_past_expiry(self):
        token = TokenInfo(
            access_token="test",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert token.is_expired()


class TestAccount:
    """Tests for Account dataclass"""
    
    def test_account_creation(self):
        account = Account(
            account_id="acc_123",
            account_name="Test Account",
            account_type="checking",
            balance=Decimal("1000.00"),
        )
        assert account.account_id == "acc_123"
        assert account.balance == Decimal("1000.00")
        assert account.currency == "USD"


class TestTransaction:
    """Tests for Transaction dataclass"""
    
    def test_transaction_creation(self):
        tx = Transaction(
            transaction_id="tx_123",
            account_id="acc_123",
            amount=Decimal("50.00"),
            date=date.today(),
            description="Test purchase",
        )
        assert tx.transaction_id == "tx_123"
        assert tx.amount == Decimal("50.00")
        assert tx.transaction_type == "debit"


class TestConnectorConfig:
    """Tests for ConnectorConfig dataclass"""
    
    def test_connector_config_defaults(self):
        config = ConnectorConfig(
            user_id=1,
            institution_id="test_bank",
        )
        assert config.user_id == 1
        assert config.institution_id == "test_bank"
        assert config.status == ConnectorStatus.DISCONNECTED


class TestMockBankConnector:
    """Tests for MockBankConnector"""
    
    def test_mock_connector_properties(self):
        connector = MockBankConnector()
        assert connector.institution_id == "mock_bank"
        assert connector.institution_name == "Mock Bank (Test)"
        assert connector.supports_oauth is True
        assert connector.supports_refresh is True
    
    def test_mock_oauth_url(self):
        connector = MockBankConnector()
        url = connector.get_authorization_url("http://localhost/callback", "test_state")
        assert "mock_auth_code_" in url
        assert "state=test_state" in url
    
    def test_mock_exchange_code(self):
        connector = MockBankConnector()
        token = connector.exchange_code("test_code", "http://localhost/callback")
        assert token.access_token.startswith("mock_access_token_")
        assert token.refresh_token.startswith("mock_refresh_token_")
        assert token.expires_at is not None
    
    def test_mock_refresh_token(self):
        connector = MockBankConnector()
        old_token = TokenInfo(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        new_token = connector.refresh_token(old_token)
        assert new_token.access_token.startswith("mock_access_token_")
        assert new_token.refresh_token == "old_refresh"
    
    def test_mock_get_accounts(self):
        connector = MockBankConnector()
        token = TokenInfo(access_token="test")
        accounts = connector.get_accounts(token)
        assert len(accounts) == 2
        assert all(isinstance(a, Account) for a in accounts)
    
    def test_mock_get_transactions(self):
        connector = MockBankConnector()
        token = TokenInfo(access_token="test")
        
        # First get accounts to have an account_id
        accounts = connector.get_accounts(token)
        account_id = accounts[0].account_id
        
        transactions = connector.get_transactions(
            token,
            account_id,
            date.today() - timedelta(days=30),
            date.today(),
        )
        assert len(transactions) > 0
        assert all(isinstance(t, Transaction) for t in transactions)
    
    def test_mock_disconnect(self):
        connector = MockBankConnector()
        token = TokenInfo(access_token="test")
        
        # Get some data first
        connector.get_accounts(token)
        
        result = connector.disconnect(token)
        assert result is True


class TestConnectorFactory:
    """Tests for connector factory"""
    
    def test_get_connector_returns_mock(self):
        connector = get_connector("mock_bank")
        assert connector is not None
        assert isinstance(connector, MockBankConnector)
    
    def test_get_connector_returns_none_for_unknown(self):
        connector = get_connector("unknown_bank")
        assert connector is None
    
    def test_list_available_connectors(self):
        connectors = list_available_connectors()
        assert len(connectors) > 0
        assert any(c["institution_id"] == "mock_bank" for c in connectors)
    
    def test_register_connector_decorator(self):
        clear_registry()
        
        @register_connector
        class CustomConnector(BaseBankConnector):
            @property
            def institution_id(self) -> str:
                return "custom_bank"
            
            @property
            def institution_name(self) -> str:
                return "Custom Bank"
            
            def get_authorization_url(self, redirect_uri: str, state: str) -> str:
                return "http://example.com/auth"
            
            def exchange_code(self, code: str, redirect_uri: str) -> TokenInfo:
                return TokenInfo(access_token="test")
            
            def refresh_token(self, token_info: TokenInfo) -> TokenInfo:
                return token_info
            
            def get_accounts(self, token_info: TokenInfo) -> list[Account]:
                return []
            
            def get_transactions(
                self,
                token_info: TokenInfo,
                account_id: str,
                start_date: date,
                end_date: date,
            ) -> list[Transaction]:
                return []
        
        connector = get_connector("custom_bank")
        assert connector is not None
        assert connector.institution_name == "Custom Bank"


class TestConnectorInterface:
    """Tests for the connector interface protocol"""
    
    def test_mock_connector_implements_interface(self):
        connector = MockBankConnector()
        # Verify it has all required methods/properties
        assert hasattr(connector, "institution_id")
        assert hasattr(connector, "institution_name")
        assert hasattr(connector, "supports_oauth")
        assert hasattr(connector, "supports_refresh")
        assert hasattr(connector, "get_authorization_url")
        assert hasattr(connector, "exchange_code")
        assert hasattr(connector, "refresh_token")
        assert hasattr(connector, "get_accounts")
        assert hasattr(connector, "get_transactions")
        assert hasattr(connector, "disconnect")
