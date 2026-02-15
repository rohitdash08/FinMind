from __future__ import annotations

from abc import ABC, abstractmethod


class BankConnector(ABC):
    provider_id: str

    @abstractmethod
    def connect(self, config: dict) -> None:
        pass

    @abstractmethod
    def import_accounts(self) -> list:
        pass

    @abstractmethod
    def import_transactions(self, cursor=None) -> tuple[list, str | None]:
        pass

    @abstractmethod
    def refresh(self, cursor=None) -> tuple[list, str | None]:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass
