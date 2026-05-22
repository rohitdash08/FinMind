import abc
from abc import ABC, abstractmethod


class BankConnector(ABC):
    @abstractmethod
    def get_transactions(self, start_date, end_date):
        pass
    
    @abstractmethod
    def import_data(self):
        pass
    
    def refresh_data(self):
        """Should be implemented by each bank"""
        pass

    @abstractmethod
    def get_accounts(self):
        pass
    
    @classmethod
    def __init_subclass__(cls, **kwargs):
        pass
    
    def get_accounts(self):
        pass
