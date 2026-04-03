"""
Tests for Universal Bank Statement Normalization Layer (#112)
"""
import pytest
import socket
from datetime import date
from decimal import Decimal

from app.services.bank_statement_normalizer import (
    normalize_statement,
    normalize_date,
    normalize_amount,
    _find_column,
    _guess_category,
    NormalizationResult,
)


def _redis_available() -> bool:
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis not available"
)


# Sample CSV fixtures
SAMPLE_CSV_STANDARD = """Date,Description,Amount
2026-03-01,Salary deposit,50000
2026-03-05,Grocery Store,-2500
2026-03-10,Netflix subscription,-500
2026-03-15,Amazon purchase,-3000
2026-03-20,ATM Withdrawal,-2000
"""

SAMPLE_CSV_DEBIT_CREDIT = """Transaction Date,Narration,Withdrawal,Deposit,Balance
01/03/2026,NEFT SALARY,,50000,150000
05/03/2026,ZOMATO FOOD DELIVERY,450,,149550
10/03/2026,AMAZON.IN,2500,,147050
15/03/2026,ATM WITHDRAWAL DR,2000,,145050
"""

SAMPLE_CSV_EUROPEAN = """Datum;Beschreibung;Betrag;Saldo
01.03.2026;Gehaltseingang;1.500,00;3.500,00
05.03.2026;Supermarkt Einkauf;-85,50;3.414,50
10.03.2026;Miete;-800,00;2.614,50
"""

SAMPLE_TSV = "Date\tDescription\tAmount\n2026-03-01\tSalary\t50000\n2026-03-05\tRent\t-15000\n"

SAMPLE_WITH_PARENS = """Date,Particulars,Amount
01-03-2026,Interest Income,1234.56
05-03-2026,Service Fee,(250.00)
10-03-2026,Refund,500
"""


class TestNormalizeDate:
    """Tests for date normalization."""

    def test_iso_format(self):
        assert normalize_date("2026-03-15") == date(2026, 3, 15)

    def test_dd_mm_yyyy_slash(self):
        assert normalize_date("15/03/2026") == date(2026, 3, 15)

    def test_dd_mm_yyyy_dash(self):
        assert normalize_date("15-03-2026") == date(2026, 3, 15)

    def test_mm_dd_yyyy(self):
        assert normalize_date("03/15/2026") == date(2026, 3, 15)

    def test_dd_mon_yyyy(self):
        assert normalize_date("15 Mar 2026") == date(2026, 3, 15)

    def test_dd_month_yyyy(self):
        assert normalize_date("15 March 2026") == date(2026, 3, 15)

    def test_yyyymmdd_compact(self):
        assert normalize_date("20260315") == date(2026, 3, 15)

    def test_dot_separated(self):
        assert normalize_date("15.03.2026") == date(2026, 3, 15)

    def test_invalid_date_returns_none(self):
        assert normalize_date("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert normalize_date("") is None

    def test_strips_whitespace(self):
        assert normalize_date("  2026-03-15  ") == date(2026, 3, 15)

    def test_strips_quotes(self):
        assert normalize_date('"2026-03-15"') == date(2026, 3, 15)


class TestNormalizeAmount:
    """Tests for amount normalization."""

    def test_simple_integer(self):
        assert normalize_amount("1234") == Decimal("1234")

    def test_decimal(self):
        assert normalize_amount("1234.56") == Decimal("1234.56")

    def test_negative(self):
        assert normalize_amount("-1234.56") == Decimal("-1234.56")

    def test_comma_thousand_separator(self):
        assert normalize_amount("1,234.56") == Decimal("1234.56")

    def test_parentheses_negative(self):
        assert normalize_amount("(1234.56)") == Decimal("-1234.56")

    def test_cr_suffix_positive(self):
        assert normalize_amount("1234.56CR") == Decimal("1234.56")

    def test_dr_suffix_negative(self):
        assert normalize_amount("1234.56DR") == Decimal("-1234.56")

    def test_currency_symbol_stripped(self):
        assert normalize_amount("₹1234.56") == Decimal("1234.56")
        assert normalize_amount("$1234.56") == Decimal("1234.56")
        assert normalize_amount("€1234.56") == Decimal("1234.56")

    def test_negate_flag(self):
        assert normalize_amount("1234", negate=True) == Decimal("-1234")

    def test_empty_returns_none(self):
        assert normalize_amount("") is None

    def test_dash_returns_none(self):
        assert normalize_amount("-") is None

    def test_na_returns_none(self):
        assert normalize_amount("N/A") is None

    def test_strips_whitespace(self):
        assert normalize_amount("  1234.56  ") == Decimal("1234.56")


class TestColumnDetection:
    """Tests for column header detection."""

    def test_finds_date_column(self):
        headers = ["Transaction Date", "Narration", "Amount"]
        assert _find_column(headers, "date") == 0

    def test_finds_description_column(self):
        headers = ["Date", "Narration", "Amount"]
        assert _find_column(headers, "description") == 1

    def test_finds_amount_column(self):
        headers = ["Date", "Description", "Transaction Amount"]
        assert _find_column(headers, "amount") == 2

    def test_finds_debit_column(self):
        headers = ["Date", "Description", "Withdrawal", "Deposit"]
        assert _find_column(headers, "debit") == 2

    def test_finds_credit_column(self):
        headers = ["Date", "Description", "Withdrawal", "Deposit"]
        assert _find_column(headers, "credit") == 3

    def test_returns_none_for_missing(self):
        headers = ["Date", "Description"]
        assert _find_column(headers, "balance") is None

    def test_case_insensitive(self):
        headers = ["DATE", "DESCRIPTION", "AMOUNT"]
        assert _find_column(headers, "date") == 0


class TestCategoryHinting:
    """Tests for category hint detection."""

    def test_salary_hint(self):
        assert "Income" in _guess_category("Monthly Salary Credit")

    def test_uber_hint(self):
        assert _guess_category("UBER TRIP") == "Transport"

    def test_zomato_hint(self):
        assert _guess_category("ZOMATO ORDER") == "Food Delivery"

    def test_netflix_hint(self):
        assert _guess_category("Netflix Subscription") == "Entertainment"

    def test_unknown_returns_empty(self):
        assert _guess_category("MISC TRANSACTION XYZ") == ""

    def test_atm_hint(self):
        assert _guess_category("ATM WITHDRAWAL") == "Cash Withdrawal"


class TestNormalizeStatement:
    """Tests for the full normalize_statement function."""

    def test_standard_csv(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        assert result.parsed_rows == 5
        assert result.skipped_rows == 0
        assert len(result.errors) == 0

    def test_debit_credit_format(self):
        result = normalize_statement(SAMPLE_CSV_DEBIT_CREDIT)
        assert result.parsed_rows >= 3  # At least 3 rows should parse

    def test_tsv_format(self):
        result = normalize_statement(SAMPLE_TSV, file_format="tsv")
        assert result.parsed_rows == 2
        assert result.detected_format == "tsv"

    def test_auto_detects_tsv(self):
        result = normalize_statement(SAMPLE_TSV, file_format="auto")
        assert result.detected_format == "tsv"

    def test_parentheses_negative_parsed(self):
        result = normalize_statement(SAMPLE_WITH_PARENS)
        service_fee = next(
            (t for t in result.transactions if "Service" in t.description), None
        )
        assert service_fee is not None
        assert service_fee.amount < 0

    def test_income_transaction_type(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        salary = next(
            (t for t in result.transactions if "Salary" in t.description), None
        )
        assert salary is not None
        assert salary.transaction_type == "INCOME"

    def test_expense_transaction_type(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        grocery = next(
            (t for t in result.transactions if "Grocery" in t.description), None
        )
        assert grocery is not None
        assert grocery.transaction_type == "EXPENSE"

    def test_empty_content_returns_error(self):
        result = normalize_statement("")
        assert result.parsed_rows == 0

    def test_transactions_have_dates(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        for t in result.transactions:
            assert isinstance(t.date, date)

    def test_category_hints_applied(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        netflix = next(
            (t for t in result.transactions if "Netflix" in t.description), None
        )
        assert netflix is not None
        assert netflix.category_hint == "Entertainment"

    def test_result_has_metadata(self):
        result = normalize_statement(SAMPLE_CSV_STANDARD)
        assert result.total_rows > 0
        assert result.detected_format in ("csv", "tsv", "unknown")


class TestBankStatementAPI:
    """HTTP endpoint tests."""

    def test_sample_formats_no_auth(self, client):
        resp = client.get("/imports/normalize-statement/sample")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "supported_formats" in data

    @requires_redis
    def test_normalize_requires_auth(self, client):
        resp = client.post("/imports/normalize-statement", json={"content": SAMPLE_CSV_STANDARD})
        assert resp.status_code == 401

    @requires_redis
    def test_normalize_returns_200(self, client, auth_header):
        resp = client.post(
            "/imports/normalize-statement",
            json={"content": SAMPLE_CSV_STANDARD},
            headers=auth_header,
        )
        assert resp.status_code == 200

    @requires_redis
    def test_missing_content_returns_400(self, client, auth_header):
        resp = client.post(
            "/imports/normalize-statement",
            json={},
            headers=auth_header,
        )
        assert resp.status_code == 400

    @requires_redis
    def test_response_has_transactions(self, client, auth_header):
        resp = client.post(
            "/imports/normalize-statement",
            json={"content": SAMPLE_CSV_STANDARD},
            headers=auth_header,
        )
        data = resp.get_json()
        assert "transactions" in data
        assert data["parsed_rows"] > 0
