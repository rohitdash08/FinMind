class MockConnector:
    def __init__(self):
        self.data_store = {}

    def get_data(self, endpoint):
        return self.data_store.get(endpoint, "Mock data for {endpoint}")

    def post_data(self, endpoint, data):
        self.data_store[endpoint] = data
        return f"Posted data to {endpoint}: {data}"

def get_transactions(self):
        return [
            {"id": 1, "amount": 100, "currency": "USD"},
            {"id": 2, "amount": 200, "currency": "EUR"}
        ]