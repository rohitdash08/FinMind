from abc import ABC, abstractmethod

class AbstractBankConnector(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

registry = {}

def register_connector(connector_name, connector_class):
    registry[connector_name] = connector_class