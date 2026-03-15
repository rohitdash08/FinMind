"""Tests for universal bank statement normalization."""

import json
import pytest


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — CSV parsing
# ═══════════════════════════════════════════════════════════════════


class TestCSVParsing:
    def test_basic_csv(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Description,Amount,Balance\n2025-01-15,Grocery Store,-50.00,1950.00\n2025-01-16,Salary,3000.00,4950.00\n"
        result = parse_csv_statement(content)

        assert result["parsed_rows"] == 2
        assert result["skipped_rows"] == 0
        txns = result["transactions"]
        assert txns[0]["amount"] == 50.0
        assert txns[0]["transaction_type"] == "debit"
        assert txns[1]["amount"] == 3000.0
        assert txns[1]["transaction_type"] == "credit"

    def test_debit_credit_columns(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Particulars,Debit,Credit,Balance\n15/01/2025,ATM Withdrawal,500,,1500\n16/01/2025,Transfer,,1000,2500\n"
        result = parse_csv_statement(content)

        assert result["parsed_rows"] == 2
        assert result["transactions"][0]["transaction_type"] == "debit"
        assert result["transactions"][0]["amount"] == 500.0
        assert result["transactions"][1]["transaction_type"] == "credit"
        assert result["transactions"][1]["amount"] == 1000.0

    def test_currency_symbols(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Description,Amount\n2025-01-15,Coffee,$4.50\n2025-01-16,Rent,₹15,000.00\n"
        result = parse_csv_statement(content)

        assert result["parsed_rows"] == 2
        assert result["transactions"][0]["amount"] == 4.5

    def test_no_headers(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        result = parse_csv_statement("")
        assert result["parsed_rows"] == 0
        assert len(result["errors"]) > 0

    def test_missing_date_column(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Description,Amount\nCoffee,5.00\n"
        result = parse_csv_statement(content)
        assert len(result["errors"]) > 0

    def test_custom_column_mapping(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Datum,Betrag,Beschreibung\n2025-01-15,-50,Einkauf\n"
        mapping = {"Datum": "date", "Betrag": "amount", "Beschreibung": "description"}
        result = parse_csv_statement(content, column_mapping=mapping)

        assert result["parsed_rows"] == 1
        assert result["transactions"][0]["description"] == "Einkauf"

    def test_custom_date_format(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Amount\n15-Jan-2025,100\n"
        result = parse_csv_statement(content, date_format="%d-%b-%Y")

        assert result["parsed_rows"] == 1
        assert result["transactions"][0]["date"] == "2025-01-15"

    def test_european_date(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Amount\n15/01/2025,-30.00\n"
        result = parse_csv_statement(content)

        assert result["parsed_rows"] == 1

    def test_skips_invalid_rows(self, client, auth_header):
        from app.services.bank_statement import parse_csv_statement

        content = "Date,Amount\n2025-01-15,100\nbaddate,200\n2025-01-17,300\n"
        result = parse_csv_statement(content)

        assert result["parsed_rows"] == 2
        assert result["skipped_rows"] == 1
        assert any("baddate" in w for w in result["warnings"])


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — OFX parsing
# ═══════════════════════════════════════════════════════════════════


class TestOFXParsing:
    def test_basic_ofx(self, client, auth_header):
        from app.services.bank_statement import parse_ofx_statement

        content = """
<OFX>
<STMTTRN>
<DTPOSTED>20250115
<TRNAMT>-50.00
<NAME>GROCERY STORE
<FITID>12345
</STMTTRN>
<STMTTRN>
<DTPOSTED>20250116
<TRNAMT>3000.00
<NAME>SALARY
<FITID>12346
</STMTTRN>
</OFX>
"""
        result = parse_ofx_statement(content)

        assert result["parsed_rows"] == 2
        assert result["transactions"][0]["amount"] == 50.0
        assert result["transactions"][0]["transaction_type"] == "debit"
        assert result["transactions"][0]["reference"] == "12345"
        assert result["transactions"][1]["transaction_type"] == "credit"

    def test_empty_ofx(self, client, auth_header):
        from app.services.bank_statement import parse_ofx_statement

        result = parse_ofx_statement("<OFX></OFX>")
        assert result["parsed_rows"] == 0

    def test_ofx_with_memo(self, client, auth_header):
        from app.services.bank_statement import parse_ofx_statement

        content = """
<STMTTRN>
<DTPOSTED>20250115
<TRNAMT>-25.00
<MEMO>Coffee Shop
<FITID>999
</STMTTRN>
"""
        result = parse_ofx_statement(content)
        assert result["parsed_rows"] == 1
        assert result["transactions"][0]["description"] == "Coffee Shop"


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Text parsing
# ═══════════════════════════════════════════════════════════════════


class TestTextParsing:
    def test_basic_text(self, client, auth_header):
        from app.services.bank_statement import parse_text_statement

        content = "15/01/2025  Grocery Store               500.00\n16/01/2025  Salary Payment            3000.00 Cr\n"
        result = parse_text_statement(content)

        assert result["parsed_rows"] >= 1

    def test_empty_text(self, client, auth_header):
        from app.services.bank_statement import parse_text_statement

        result = parse_text_statement("")
        assert result["parsed_rows"] == 0


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Format detection and column detection
# ═══════════════════════════════════════════════════════════════════


class TestDetection:
    def test_detect_csv(self, client, auth_header):
        from app.services.bank_statement import detect_statement_format

        assert detect_statement_format("a,b,c\n1,2,3", "data.csv") == "csv"
        assert detect_statement_format("Date,Amount,Desc\n1,2,3") == "csv"

    def test_detect_ofx(self, client, auth_header):
        from app.services.bank_statement import detect_statement_format

        assert detect_statement_format("<OFX>...", "stmt.ofx") == "ofx"
        assert detect_statement_format("<OFX>something") == "ofx"
        assert detect_statement_format("", "data.qfx") == "ofx"

    def test_detect_text(self, client, auth_header):
        from app.services.bank_statement import detect_statement_format

        assert detect_statement_format("some plain text\ndata here") == "text"

    def test_detect_columns(self, client, auth_header):
        from app.services.bank_statement import detect_columns

        mapping = detect_columns(["Date", "Description", "Amount", "Balance"])
        assert mapping["Date"] == "date"
        assert mapping["Description"] == "description"
        assert mapping["Amount"] == "amount"
        assert mapping["Balance"] == "balance"

    def test_detect_columns_aliases(self, client, auth_header):
        from app.services.bank_statement import detect_columns

        mapping = detect_columns(["Transaction Date", "Narrative", "Debit", "Credit"])
        assert mapping["Transaction Date"] == "date"
        assert mapping["Narrative"] == "description"
        assert mapping["Debit"] == "debit"
        assert mapping["Credit"] == "credit"


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Main entry point
# ═══════════════════════════════════════════════════════════════════


class TestNormalizeStatement:
    def test_auto_detect_csv(self, client, auth_header):
        from app.services.bank_statement import normalize_statement

        content = "Date,Amount,Description\n2025-01-15,-50,Coffee\n"
        result = normalize_statement(content)

        assert result["detected_format"] == "csv"
        assert result["parsed_rows"] == 1

    def test_force_format(self, client, auth_header):
        from app.services.bank_statement import normalize_statement

        content = "Date,Amount\n2025-01-15,100\n"
        result = normalize_statement(content, file_format="csv")
        assert result["detected_format"] == "csv"

    def test_summary_stats(self, client, auth_header):
        from app.services.bank_statement import normalize_statement

        content = "Date,Amount\n2025-01-15,-50\n2025-01-16,3000\n2025-01-17,-100\n"
        result = normalize_statement(content, file_format="csv")

        assert result["summary"]["total_transactions"] == 3
        assert result["summary"]["total_debits"] == 2
        assert result["summary"]["total_credits"] == 1


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Amount parsing
# ═══════════════════════════════════════════════════════════════════


class TestAmountParsing:
    def test_parse_various_formats(self, client, auth_header):
        from app.services.bank_statement import parse_amount

        assert parse_amount("50.00") == 50.0
        assert parse_amount("-100.50") == -100.5
        assert parse_amount("$1,234.56") == 1234.56
        assert parse_amount("₹15,000") == 15000.0
        assert parse_amount("") is None
        assert parse_amount("abc") is None

    def test_european_format(self, client, auth_header):
        from app.services.bank_statement import parse_amount

        assert parse_amount("1.234,56") == 1234.56


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestStatementRoutes:
    def test_normalize_csv(self, client, auth_header):
        r = client.post(
            "/statements/normalize",
            headers=auth_header,
            json={
                "content": "Date,Amount,Description\n2025-01-15,-50,Coffee\n",
                "format": "csv",
            },
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["parsed_rows"] == 1
        assert body["detected_format"] == "csv"

    def test_normalize_missing_content(self, client, auth_header):
        r = client.post("/statements/normalize", headers=auth_header, json={})
        assert r.status_code == 400

    def test_normalize_unauthorized(self, client):
        r = client.post("/statements/normalize", json={"content": "x"})
        assert r.status_code == 401

    def test_detect_format_route(self, client, auth_header):
        r = client.post(
            "/statements/detect-format",
            headers=auth_header,
            json={"content": "<OFX>data", "filename": "stmt.ofx"},
        )
        assert r.status_code == 200
        assert r.get_json()["format"] == "ofx"

    def test_detect_format_missing(self, client, auth_header):
        r = client.post("/statements/detect-format", headers=auth_header, json={})
        assert r.status_code == 400

    def test_detect_columns_route(self, client, auth_header):
        r = client.post(
            "/statements/detect-columns",
            headers=auth_header,
            json={"headers": ["Date", "Amount", "Description"]},
        )
        assert r.status_code == 200
        mapping = r.get_json()["column_mapping"]
        assert mapping["Date"] == "date"

    def test_detect_columns_missing(self, client, auth_header):
        r = client.post("/statements/detect-columns", headers=auth_header, json={})
        assert r.status_code == 400

    def test_detect_columns_unauthorized(self, client):
        r = client.post("/statements/detect-columns", json={"headers": ["Date"]})
        assert r.status_code == 401
