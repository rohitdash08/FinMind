from __future__ import annotations

from .mock_connector import MockBankConnector
from .providers.aa_provider import AAProviderConnector


class ConnectorRegistry:
    def __init__(self):
        self._connectors = {}

    def register(self, connector):
        self._connectors[connector.provider_id] = connector

    def get(self, provider_id):
        return self._connectors.get(provider_id)

    def list(self):
        return list(self._connectors.keys())


registry = ConnectorRegistry()
registry.register(MockBankConnector())
registry.register(AAProviderConnector())
