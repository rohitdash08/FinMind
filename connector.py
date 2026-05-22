import abc


class BankConnector(abc.ABC):
    """Base class for all bank connectors"""
    
    def __init__(self):
        self.type = "bank_connector"
    
    @abc.abstractmethod
    def connect(self, user_id):
        pass
    
    @abc.abstractmethod
    def refresh_data(self, user_id):
        pass