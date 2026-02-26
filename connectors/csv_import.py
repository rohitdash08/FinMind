"""CSV file import connector for manual bank statement imports."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from connectors.base import BankConnector, ConnectorError
from models.transaction import (
    Account, AccountType, Balance, Currency, Transaction,
    TransactionStatus, TransactionType,
)

logger = logging.getLogger(__name__)

# Common CSV column name mappings
_DEFAULT_COLUMN_MAP: Dict[str, str] = {
    "date": "date",
    "amount": "amount",
    "description": "description",
    "category": "category",
    "type": "type",
    "status": "status",
    "merchant": "merchant_name",
    "balance": "balance",
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%m/%d/%y",
    "%d-%m-%Y",
]


class CSVConnector(BankConnector):
    """Connector for importing transactions from CSV bank statements.

    Config keys:
        file_path: Path to the CSV file (or set via load_file())
        account_name: Name for the imported account (default: 'CSV Import')
        column_map: Dict mapping our field names to CSV column headers
        date_format: strptime format string (auto-detected if omitted)
        delimiter: CSV delimiter (default: ',')
        encoding: File encoding (default: 'utf-8')
        skip_rows: Number of header rows to skip (default: 0)
    """

    def __init__(self, connector_id: str = "csv-1", config: Optional[dict] = None):
        super().__init__(connector_id, config)
        self._file_path: Optional[Path] = None
        self._account: Optional[Account] = None
        self._transactions: List[Transaction] = []
        self._detected_date_format: Optional[str] = None

    @property
    def name(self) -> str:
        return "CSV Import"

    @property
    def connector_type(self) -> str:
        return "csv"

    def connect(self) -> None:
        """Initialize the CSV connector and load file if configured."""
        file_path = self.config.get("file_path")
        if file_path:
            self._file_path = Path(file_path)
            if not self._file_path.exists():
                raise ConnectorError(f"CSV file not found: {self._file_path}")

        account_name = self.config.get("account_name", "CSV Import")
        self._account = Account(
            account_id=f"{self.connector_id}-csv",
            name=account_name,
            account_type=AccountType.CHECKING,
            institution_name="CSV Import",
        )
        self._connected = True
        self._logger.info("CSV connector ready.")

        if self._file_path:
            self._load_csv()

    def disconnect(self) -> None:
        self._connected = False
        self._transactions.clear()
        self._account = None
        self._file_path = None
        self._detected_date_format = None

    def load_file(self, file_path: str) -> int:
        """Load a CSV file and return the number of transactions parsed.

        Args:
            file_path: Path to the CSV file.

        Returns:
            Number of transactions imported.
        """
        self._ensure_connected()
        self._file_path = Path(file_path)
        if not self._file_path.exists():
            raise ConnectorError(f"CSV file not found: {self._file_path}")
        self._transactions.clear()
        self._load_csv()
        return len(self._transactions)

    def get_accounts(self) -> List[Account]:
        self._ensure_connected()
        return [self._account] if self._account else []

    def get_balance(self, account_id: str) -> Balance:
        self._ensure_connected()
        if not self._account or account_id != self._account.account_id:
            raise ConnectorError(f"Account {account_id!r} not found.")
        total = sum(t.amount for t in self._transactions)
        return Balance(account_id=account_id, current=round(total, 2), available=round(total, 2))

    def import_transactions(
        self, start_date: datetime, end_date: datetime, account_id: Optional[str] = None
    ) -> List[Transaction]:
        self._ensure_connected()
        return [
            t for t in self._transactions
            if start_date <= t.date <= end_date
        ]

    def refresh(self) -> List[Transaction]:
        """Re-read the CSV file and return all transactions."""
        self._ensure_connected()
        if self._file_path and self._file_path.exists():
            self._transactions.clear()
            self._load_csv()
        return list(self._transactions)

    def _load_csv(self) -> None:
        """Parse the CSV file into Transaction objects."""
        if not self._file_path:
            raise ConnectorError("No CSV file configured.")

        delimiter = self.config.get("delimiter", ",")
        encoding = self.config.get("encoding", "utf-8")
        skip_rows = self.config.get("skip_rows", 0)
        col_map = {**_DEFAULT_COLUMN_MAP, **(self.config.get("column_map") or {})}

        try:
            with open(self._file_path, "r", encoding=encoding, newline="") as f:
                for _ in range(skip_rows):
                    next(f)
                reader = csv.DictReader(f, delimiter=delimiter)
                if not reader.fieldnames:
                    raise ConnectorError("CSV file has no headers.")

                # Normalize headers
                header_map = self._build_header_map(reader.fieldnames, col_map)
                self._logger.debug("Column mapping: %s", header_map)

                for i, row in enumerate(reader):
                    try:
                        txn = self._parse_row(row, header_map, i)
                        if txn:
                            self._transactions.append(txn)
                    except Exception as e:
                        self._logger.warning("Skipping row %d: %s", i + 1, e)

            self._logger.info("Loaded %d transactions from %s", len(self._transactions), self._file_path.name)

        except ConnectorError:
            raise
        except Exception as e:
            raise ConnectorError(f"Failed to read CSV: {e}")

    def _build_header_map(self, fieldnames: List[str], col_map: Dict[str, str]) -> Dict[str, str]:
        """Map our internal field names to actual CSV column names."""
        normalized = {h.strip().lower().replace(" ", "_"): h for h in fieldnames}
        result: Dict[str, str] = {}
        for our_key, csv_key in col_map.items():
            csv_lower = csv_key.strip().lower().replace(" ", "_")
            if csv_lower in normalized:
                result[our_key] = normalized[csv_lower]
            elif csv_key in fieldnames:
                result[our_key] = csv_key
        return result

    def _parse_row(self, row: Dict[str, str], header_map: Dict[str, str], idx: int) -> Optional[Transaction]:
        """Parse a single CSV row into a Transaction."""
        date_col = header_map.get("date")
        amount_col = header_map.get("amount")
        desc_col = header_map.get("description")

        if not date_col or not amount_col:
            raise ConnectorError("CSV must have at least 'date' and 'amount' columns.")

        raw_date = row.get(date_col, "").strip()
        raw_amount = row.get(amount_col, "").strip()

        if not raw_date or not raw_amount:
            return None

        date = self._parse_date(raw_date)
        amount = self._parse_amount(raw_amount)
        description = row.get(desc_col, "").strip() if desc_col else ""
        category = row.get(header_map.get("category", ""), "").strip()
        merchant = row.get(header_map.get("merchant_name", ""), "").strip()

        ttype = TransactionType.DEBIT if amount < 0 else TransactionType.CREDIT

        return Transaction(
            transaction_id=f"{self.connector_id}-csv-{idx}",
            account_id=self._account.account_id if self._account else "",
            amount=amount,
            date=date,
            description=description,
            transaction_type=ttype,
            status=TransactionStatus.POSTED,
            category=category,
            merchant_name=merchant,
        )

    def _parse_date(self, raw: str) -> datetime:
        """Parse a date string, auto-detecting format."""
        if self._detected_date_format:
            try:
                return datetime.strptime(raw, self._detected_date_format)
            except ValueError:
                pass

        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(raw, fmt)
                self._detected_date_format = fmt
                return dt
            except ValueError:
                continue

        raise ConnectorError(f"Unable to parse date: {raw!r}")

    @staticmethod
    def _parse_amount(raw: str) -> float:
        """Parse an amount string, handling currency symbols and commas."""
        cleaned = raw.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
        try:
            return round(float(cleaned), 2)
        except ValueError:
            raise ConnectorError(f"Unable to parse amount: {raw!r}")
