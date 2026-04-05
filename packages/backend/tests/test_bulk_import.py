"""Tests for bulk import validation (issue #115)."""

def test_valid_csv():
    from app.services.bulk_import import parse_csv
    csv = "amount,spent_at,notes\n100,2026-04-01,Groceries\n50,2026-04-02,Coffee"
    result = parse_csv(csv)
    assert result["valid"] is True
    assert result["row_count"] == 2
    assert result["preview"][0]["amount"] == 100.0

def test_missing_required_column():
    from app.services.bulk_import import parse_csv
    csv = "notes,spent_at\ntest,2026-04-01"
    result = parse_csv(csv)
    assert result["valid"] is False
    assert any("amount" in e for e in result["errors"])

def test_invalid_amount():
    from app.services.bulk_import import parse_csv
    csv = "amount,spent_at\nabc,2026-04-01"
    result = parse_csv(csv)
    assert result["valid"] is False
    assert any("amount" in e for e in result["errors"])

def test_invalid_date():
    from app.services.bulk_import import parse_csv
    csv = "amount,spent_at\n100,not-a-date"
    result = parse_csv(csv)
    assert result["valid"] is False
    assert any("date" in e for e in result["errors"])

def test_unknown_columns_warn():
    from app.services.bulk_import import parse_csv
    csv = "amount,spent_at,mystery_col\n100,2026-04-01,x"
    result = parse_csv(csv)
    assert any("mystery_col" in w for w in result["warnings"])
