from .bank_connector import AbstractBankConnector, register_connector

# Wire up all routes here
def wire_up_routes():
    # Example route registration
    register_connector('example', ExampleBankConnector)

class ExampleBankConnector(AbstractBankConnector):
    def connect(self):
        print("Connecting to example bank")

    def disconnect(self):
        print("Disconnecting from example bank")