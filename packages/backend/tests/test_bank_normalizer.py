"""Tests for bank statement normalization (issue #112)."""

def test_detect_chase():
    from app.services.bank_normalizer import _detect_bank
    assert _detect_bank({"Transaction Date", "Post Date", "Category", "Amount"}) == "chase"

def test_detect_generic():
    from app.services.bank_normalizer import _detect_bank
    assert _detect_bank({"date", "amount", "memo"}) == "generic"

def test_normalize_generic_csv():
    from app.services.bank_normalizer import normalize_statement
    csv = "date,amount,description\n2026-04-01,-50.00,Groceries\n2026-04-02,1000,Salary"
    result = normalize_statement(csv)
    assert result["row_count"] == 2
    assert result["rows"][0]["type"] == "EXPENSE"
    assert result["rows"][1]["type"] == "INCOME"

def test_parse_date_formats():
    from app.services.bank_normalizer import _parse_date
    from datetime import date
    assert _parse_date("04/01/2026") == date(2026, 4, 1)
    assert _parse_date("2026-04-01") == date(2026, 4, 1)
    assert _parse_date("not-a-date") is None

def test_invalid_rows_reported():
    from app.services.bank_normalizer import normalize_statement
    csv = "date,amount\nbaddate,100\n2026-04-01,notanumber"
    result = normalize_statement(csv)
    assert len(result["errors"]) == 2
