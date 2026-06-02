"""Plaid Bank Connector - Real Bank Integration."""

import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .base import (
    BankConnector,
    ConnectionCredentials,
    BankAccount,
    Transaction,
    ConnectionStatus,
    AuthenticationError,
    ConnectionError,
    AccountNotFoundError,
)

# Optional: Import plaid if available
try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.item_remove_request import ItemRemoveRequest
    from plaid.configuration import Configuration
    from plaid.api_client import ApiClient
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False


class PlaidConnector(BankConnector):
    """Plaid-powered bank connector for real bank integrations."""
    
    name = "plaid"
    display_name = "Plaid (Production)"
    description = "Connect to 12,000+ financial institutions via Plaid"
    supported_countries = ["US", "CA", "GB", "IE", "FR", "ES", "NL"]
    features = ["transactions", "balance", "oauth", "refresh", "webhooks", "auth"]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        cfg = config or {}
        self.client_id = cfg.get('client_id') or os.getenv('PLAID_CLIENT_ID')
        self.secret = cfg.get('secret') or os.getenv('PLAID_SECRET')
        self.environment = cfg.get('environment', 'sandbox')
        self._client = None
        
    def _get_client(self):
        """Initialize Plaid client."""
        if self._client:
            return self._client
            
        if not PLAID_AVAILABLE:
            raise ConnectionError("Plaid SDK not installed. Run: pip install plaid-python")
            
        if not self.client_id or not self.secret:
            raise ConnectionError("Plaid credentials not configured")
        
        configuration = Configuration(
            host=getattr(plaid.Environment, self.environment.upper(), plaid.Environment.sandbox),
            api_key={
                'clientId': self.client_id,
                'secret': self.secret,
            }
        )
        api_client = ApiClient(configuration)
        self._client = plaid_api.PlaidApi(api_client)
        return self._client
    
    def connect(self, credentials: ConnectionCredentials) -> Dict[str, Any]:
        """Exchange public token for access token."""
        if not credentials.additional_data:
            raise AuthenticationError("No public token provided")
        
        public_token = credentials.additional_data.get('public_token')
        if not public_token:
            raise AuthenticationError("Public token required")
        
        try:
            client = self._get_client()
            exchange_request = ItemPublicTokenExchangeRequest(
                public_token=public_token
            )
            exchange_response = client.item_public_token_exchange(exchange_request)
            
            access_token = exchange_response['access_token']
            item_id = exchange_response['item_id']
            
            return {
                'connection_id': item_id,
                'status': ConnectionStatus.CONNECTED,
                'access_token': access_token,
                'institution_name': credentials.additional_data.get('institution_name', 'Unknown'),
                'environment': self.environment
            }
            
        except Exception as e:
            raise AuthenticationError(f"Failed to connect: {str(e)}")
    
    def validate_credentials(self, credentials: ConnectionCredentials) -> bool:
        """Validate access token."""
        if not credentials.access_token:
            return False
        return credentials.access_token.startswith('access-')
    
    def refresh_connection(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        """Plaid access tokens don't expire, but we simulate refresh."""
        return ConnectionCredentials(
            access_token=credentials.access_token,
            expires_at=datetime.utcnow() + timedelta(days=90),
            additional_data=credentials.additional_data
        )
    
    def get_accounts(self, credentials: ConnectionCredentials) -> List[BankAccount]:
        """Fetch accounts from Plaid."""
        if not self.validate_credentials(credentials):
            raise AuthenticationError("Invalid credentials")
        
        try:
            client = self._get_client()
            request = AccountsGetRequest(access_token=credentials.access_token)
            response = client.accounts_get(request)
            
            accounts = []
            for acc in response['accounts']:
                accounts.append(BankAccount(
                    id=acc['account_id'],
                    name=acc['name'],
                    account_type=acc['type'],
                    currency=acc['balances']['iso_currency_code'] or 'USD',
                    balance=float(acc['balances']['current'] or 0),
                    available_balance=float(acc['balances']['available'] or 0) if acc['balances']['available'] else None,
                    masked_number=acc['mask'],
                    institution_name=credentials.additional_data.get('institution_name') if credentials.additional_data else None
                ))
            return accounts
            
        except Exception as e:
            raise ConnectionError(f"Failed to fetch accounts: {str(e)}")
    
    def get_transactions(
        self,
        credentials: ConnectionCredentials,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """Fetch transactions from Plaid."""
        if not self.validate_credentials(credentials):
            raise AuthenticationError("Invalid credentials")
        
        # Default to last 30 days
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        try:
            client = self._get_client()
            
            request = TransactionsGetRequest(
                access_token=credentials.access_token,
                start_date=start_date.date(),
                end_date=end_date.date(),
                options=TransactionsGetRequestOptions(
                    account_ids=[account_id]
                )
            )
            
            response = client.transactions_get(request)
            
            transactions = []
            for txn in response['transactions']:
                transactions.append(Transaction(
                    id=txn['transaction_id'],
                    account_id=account_id,
                    amount=-float(txn['amount']) if txn['amount'] > 0 else float(txn['amount']),
                    currency=txn['iso_currency_code'] or 'USD',
                    description=txn['name'],
                    transaction_date=datetime.strptime(txn['date'], '%Y-%m-%d'),
                    merchant_name=txn.get('merchant_name'),
                    pending=txn['pending']
                ))
            return transactions
            
        except Exception as e:
            raise ConnectionError(f"Failed to fetch transactions: {str(e)}")
    
    def get_balance(self, credentials: ConnectionCredentials, account_id: str) -> BankAccount:
        """Get account balance."""
        accounts = self.get_accounts(credentials)
        for account in accounts:
            if account.id == account_id:
                return account
        raise AccountNotFoundError(f"Account {account_id} not found")
    
    def disconnect(self, credentials: ConnectionCredentials) -> bool:
        """Remove Plaid item."""
        try:
            client = self._get_client()
            request = ItemRemoveRequest(access_token=credentials.access_token)
            client.item_remove(request)
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to disconnect: {str(e)}")
    
    def get_connection_status(self, credentials: ConnectionCredentials) -> ConnectionStatus:
        """Check connection status."""
        try:
            # Try to fetch accounts to verify connection
            self.get_accounts(credentials)
            return ConnectionStatus.CONNECTED
        except Exception:
            return ConnectionStatus.ERROR
