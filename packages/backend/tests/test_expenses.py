from io import BytesIO


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    return r.get_json()[0]["id"]


def test_expenses_crud_filters_and_canonical_fields(client, auth_header):
    cat_id = _create_category(client, auth_header)

    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    payload = {
        "amount": 12.5,
        "currency": "USD",
        "category_id": cat_id,
        "description": "Groceries",
        "date": "2026-02-12",
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    created = r.get_json()
    exp_id = created["id"]
    assert created["description"] == "Groceries"
    assert created["date"] == "2026-02-12"
    assert created["amount"] == 12.5

    r = client.patch(
        f"/expenses/{exp_id}",
        json={"description": "Groceries + milk", "amount": 15.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["description"] == "Groceries + milk"
    assert updated["amount"] == 15.0

    r = client.get("/expenses?search=milk", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == exp_id

    r = client.get("/expenses?from=2026-02-01&to=2026-02-28", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    r = client.delete(f"/expenses/{exp_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_expense_create_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "INR"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {
        "amount": 99.5,
        "description": "Local travel",
        "date": "2026-02-12",
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    created = r.get_json()
    assert created["currency"] == "INR"


def test_expense_import_preview_and_commit_prevents_duplicates(client, auth_header):
    cat_id = _create_category(client, auth_header)

    csv_data = (
        "date,amount,description,category_id\n"
        "2026-02-10,10.50,Coffee,{}\n"
        "2026-02-11,22.00,Lunch,\n".format(cat_id)
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    preview = r.get_json()
    assert preview["total"] == 2
    assert preview["duplicates"] == 0
    assert preview["transactions"][0]["description"] == "Coffee"

    r = client.post(
        "/expenses/import/commit",
        json={"transactions": preview["transactions"]},
        headers=auth_header,
    )
    assert r.status_code == 201
    committed = r.get_json()
    assert committed["inserted"] == 2
    assert committed["duplicates"] == 0

    r = client.post(
        "/expenses/import/commit",
        json={"transactions": preview["transactions"]},
        headers=auth_header,
    )
    assert r.status_code == 201
    second = r.get_json()
    assert second["inserted"] == 0
    assert second["duplicates"] == 2


def test_expense_import_preview_pdf_uses_extractor(client, auth_header, monkeypatch):
    _create_category(client, auth_header)

    def _fake_extract(*args, **kwargs):
        return [
            {
                "date": "2026-02-10",
                "amount": 7.5,
                "description": "Bus",
                "category_id": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.expense_import.extract_transactions_from_statement",
        _fake_extract,
    )

    data = {"file": (BytesIO(b"%PDF-1.4 fake"), "statement.pdf")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total"] == 1
    assert payload["transactions"][0]["description"] == "Bus"


def test_expense_import_preview_pdf_fallback_without_gemini(
    client, auth_header, monkeypatch
):
    _create_category(client, auth_header)

    sample_text = "\n".join(
        [
            "2026-02-10 Coffee Shop -4.50",
            "2026-02-11 Payroll Deposit 2500.00",
        ]
    )
    monkeypatch.setattr(
        "app.services.expense_import._extract_pdf_text",
        lambda _data: sample_text,
    )

    data = {"file": (BytesIO(b"%PDF-1.4 fake"), "statement.pdf")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total"] == 2
    assert payload["duplicates"] == 0
    tx = payload["transactions"]
    assert tx[0]["description"] == "Coffee Shop"
    assert tx[0]["amount"] == 4.5
    assert tx[0]["expense_type"] == "EXPENSE"
    assert tx[1]["description"] == "Payroll Deposit"
    assert tx[1]["amount"] == 2500.0
    assert tx[1]["expense_type"] == "INCOME"


def test_recurring_expense_create_list_and_generate(client, auth_header):
    cat_id = _create_category(client, auth_header, name="Rent")

    create_payload = {
        "amount": 1500.0,
        "description": "House Rent",
        "category_id": cat_id,
        "cadence": "MONTHLY",
        "start_date": "2026-01-05",
        "end_date": "2026-03-31",
    }
    r = client.post("/expenses/recurring", json=create_payload, headers=auth_header)
    assert r.status_code == 201
    recurring = r.get_json()
    recurring_id = recurring["id"]
    assert recurring["cadence"] == "MONTHLY"
    assert recurring["description"] == "House Rent"
    assert recurring["currency"] == "INR"

    r = client.get("/expenses/recurring", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == recurring_id

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-03-31"},
        headers=auth_header,
    )
    assert r.status_code == 200
    gen = r.get_json()
    assert gen["inserted"] == 3

    # Second run for same window should not duplicate generated rows.
    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-03-31"},
        headers=auth_header,
    )
    assert r.status_code == 200
    gen2 = r.get_json()
    assert gen2["inserted"] == 0

    r = client.get("/expenses?search=House%20Rent", headers=auth_header)
    assert r.status_code == 200
    generated = r.get_json()
    assert len(generated) == 3


def test_recurring_expense_generate_respects_end_date(client, auth_header):
    create_payload = {
        "amount": 100.0,
        "description": "Gym Membership",
        "cadence": "WEEKLY",
        "start_date": "2026-01-01",
        "end_date": "2026-01-15",
    }
    r = client.post("/expenses/recurring", json=create_payload, headers=auth_header)
    assert r.status_code == 201
    recurring_id = r.get_json()["id"]

    r = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": "2026-02-28"},
        headers=auth_header,
    )
    assert r.status_code == 200
    gen = r.get_json()
    assert gen["inserted"] == 3

    r = client.get("/expenses?search=Gym%20Membership", headers=auth_header)
    assert r.status_code == 200
    generated = r.get_json()
    assert len(generated) == 3


# ---------------------------------------------------------------------------
# Tests for Bulk Import Validation & Preview (issue #115)
# ---------------------------------------------------------------------------

from io import BytesIO


def test_import_preview_returns_validation_results(client, auth_header):
    """Preview endpoint now returns per-row validation, warnings, and corrections."""
    csv_data = (
        "date,amount,description,currency\n"
        "2026-02-10,10.50,Coffee,USD\n"
        "2026-02-11,22.00,Lunch,USD\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    # New validation fields
    assert "valid_rows" in payload
    assert "warning_rows" in payload
    assert "error_rows" in payload
    assert "ready_to_import" in payload
    assert "row_validations" in payload
    # Valid data: 2 rows should be valid
    assert payload["valid_rows"] == 2
    assert payload["error_rows"] == 0
    assert payload["ready_to_import"] is True
    assert len(payload["row_validations"]) == 2


def test_import_preview_flags_invalid_date(client, auth_header):
    """Rows with invalid dates are flagged as errors."""
    csv_data = (
        "date,amount,description\n"
        "NOT-A-DATE,10.50,Coffee\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["error_rows"] >= 1
    assert payload["ready_to_import"] is False
    v = payload["row_validations"][0]
    assert v["has_errors"] is True
    assert any("date" in w.lower() for w in v["warnings"])


def test_import_preview_flags_zero_amount_warning_by_default(client, auth_header):
    """Zero-amount rows produce a warning but are not blocking errors by default."""
    csv_data = (
        "date,amount,description\n"
        "2026-02-10,0,Refund Adjustment\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    # Zero amount is a warning, not an error, so ready_to_import still True
    assert payload["error_rows"] == 0
    assert payload["warning_rows"] >= 1
    assert payload["ready_to_import"] is True


def test_import_preview_strict_zero_amount_blocks_import(client, auth_header):
    """With strict=true, zero amounts block the import."""
    csv_data = (
        "date,amount,description\n"
        "2026-02-10,0,Refund Adjustment\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview?strict=true",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["error_rows"] >= 1
    assert payload["ready_to_import"] is False


def test_import_preview_auto_corrects_missing_description(client, auth_header):
    """Missing descriptions are auto-corrected to 'Unknown'."""
    csv_data = (
        "date,amount,description,currency\n"
        "2026-02-10,10.50,,USD\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    # Missing description should be corrected
    assert "description" in v["corrections"]
    assert v["corrections"]["description"] == "Unknown"
    # And the original row in transactions should reflect the correction
    tx = payload["transactions"][0]
    assert tx["description"] == "Unknown"


def test_import_preview_auto_corrects_missing_currency(client, auth_header):
    """Missing currency defaults to USD."""
    csv_data = (
        "date,amount,description,currency\n"
        "2026-02-10,10.50,Coffee,\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    assert "currency" in v["corrections"]
    assert v["corrections"]["currency"] == "USD"


def test_import_preview_corrects_unknown_expense_type(client, auth_header):
    """Unknown expense_type is corrected to EXPENSE."""
    csv_data = (
        "date,amount,description,expense_type\n"
        "2026-02-10,10.50,Coffee,UNKNOWN_TYPE\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    assert v["corrections"].get("expense_type") == "EXPENSE"
    assert any("expense_type" in w.lower() for w in v["warnings"])


def test_import_preview_flags_future_date_in_strict_mode(client, auth_header):
    """Future dates are flagged in strict mode."""
    csv_data = (
        "date,amount,description\n"
        "2099-12-31,10.50,Coffee\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview?strict=true",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["error_rows"] >= 1
    assert payload["ready_to_import"] is False


def test_import_preview_shows_duplicate_warning(client, auth_header):
    """Existing transactions are flagged as potential duplicates in preview."""
    # First import
    csv1 = (
        "date,amount,description\n"
        "2026-02-10,10.50,Coffee\n"
    )
    data1 = {"file": (BytesIO(csv1.encode("utf-8")), "s1.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data1,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    preview = r.get_json()
    r = client.post(
        "/expenses/import/commit",
        json={"transactions": preview["transactions"]},
        headers=auth_header,
    )
    assert r.status_code == 201

    # Preview again — should flag as duplicate
    r = client.post(
        "/expenses/import/preview",
        data=data1,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    assert any("duplicate" in w.lower() for w in v["warnings"])


def test_import_preview_large_amount_warns(client, auth_header):
    """Amounts over 100000 are flagged as unusually large."""
    csv_data = (
        "date,amount,description\n"
        "2026-02-10,150000.00,House Deposit\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    assert any("large amount" in w.lower() or "150000" in w for w in v["warnings"])


def test_import_preview_very_old_date_warns(client, auth_header):
    """Dates before 1990-01-01 produce a warning."""
    csv_data = (
        "date,amount,description\n"
        "1980-01-01,10.50,Coffee\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    v = payload["row_validations"][0]
    assert any("very old" in w.lower() for w in v["warnings"])


def test_import_preview_corrections_applied_to_transactions(client, auth_header):
    """Auto-corrections are reflected in the returned transactions list."""
    csv_data = (
        "date,amount,description,currency,expense_type\n"
        "2026-02-10,10.50,,,\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/expenses/import/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    tx = payload["transactions"][0]
    # Corrections should be applied to the transaction
    assert tx["description"] == "Unknown"
    assert tx["currency"] == "USD"
    assert tx["expense_type"] == "EXPENSE"


# ---------------------------------------------------------------------------
# Standalone unit tests for the validation service
# ---------------------------------------------------------------------------

from app.services.expense_import import validate_import_rows, _parse_date, _parse_float


def test_validate_import_rows_all_valid():
    rows = [
        {"date": "2026-01-15", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"},
        {"date": "2026-01-16", "amount": 1000.0, "description": "Rent", "expense_type": "EXPENSE", "currency": "USD"},
    ]
    result = validate_import_rows(rows)
    assert result.total_rows == 2
    assert result.valid_rows == 2
    assert result.warning_rows == 0
    assert result.error_rows == 0
    assert result.ready_to_import is True


def test_validate_import_rows_invalid_date():
    rows = [{"date": "NOT-A-DATE", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows)
    assert result.error_rows == 1
    assert result.ready_to_import is False
    v = result.row_results[0]
    assert v.has_errors is True
    assert any("date" in w.lower() for w in v.warnings)


def test_validate_import_rows_missing_amount():
    rows = [{"date": "2026-01-15", "amount": None, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows)
    assert result.error_rows == 1
    assert result.ready_to_import is False


def test_validate_import_rows_zero_amount_warning():
    rows = [{"date": "2026-01-15", "amount": 0, "description": "Adjustment", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows, strict=False)
    assert result.error_rows == 0
    assert result.warning_rows == 1
    assert result.ready_to_import is True
    assert any("zero" in w.lower() for w in result.row_results[0].warnings)


def test_validate_import_rows_zero_amount_strict_blocks():
    rows = [{"date": "2026-01-15", "amount": 0, "description": "Adjustment", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows, strict=True)
    assert result.error_rows == 1
    assert result.ready_to_import is False


def test_validate_import_rows_missing_description_auto_corrected():
    rows = [{"date": "2026-01-15", "amount": 5.0, "description": "", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows)
    v = result.row_results[0]
    assert v.corrections["description"] == "Unknown"
    assert any("missing description" in w.lower() for w in v.warnings)
    assert result.row_results[0].is_valid is True  # warning only, not error


def test_validate_import_rows_missing_currency_auto_corrected():
    rows = [{"date": "2026-01-15", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": ""}]
    result = validate_import_rows(rows)
    v = result.row_results[0]
    assert v.corrections["currency"] == "USD"
    assert any("currency" in w.lower() for w in v.warnings)


def test_validate_import_rows_unknown_expense_type_corrected():
    rows = [{"date": "2026-01-15", "amount": 5.0, "description": "Coffee", "expense_type": "GARBAGE", "currency": "USD"}]
    result = validate_import_rows(rows)
    v = result.row_results[0]
    assert v.corrections["expense_type"] == "EXPENSE"


def test_validate_import_rows_future_date_strict_blocks():
    rows = [{"date": "2099-01-15", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows, strict=True)
    assert result.error_rows == 1
    assert result.ready_to_import is False


def test_validate_import_rows_future_date_non_strict_warns():
    rows = [{"date": "2099-01-15", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows, strict=False)
    assert result.error_rows == 0
    assert result.warning_rows == 1
    assert result.ready_to_import is True


def test_validate_import_rows_very_old_date_warns():
    rows = [{"date": "1980-01-01", "amount": 5.0, "description": "Coffee", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows)
    assert result.warning_rows == 1
    assert any("very old" in w.lower() for w in result.row_results[0].warnings)


def test_validate_import_rows_large_amount_warns():
    rows = [{"date": "2026-01-15", "amount": 500_000.0, "description": "Car", "expense_type": "EXPENSE", "currency": "USD"}]
    result = validate_import_rows(rows)
    assert result.warning_rows == 1
    assert any("large amount" in w.lower() or "500000" in w for w in result.row_results[0].warnings)


def test_validate_import_rows_empty_list():
    result = validate_import_rows([])
    assert result.total_rows == 0
    assert result.valid_rows == 0
    assert result.ready_to_import is False


def test_parse_date_various_formats():
    assert _parse_date("2026-01-15") == date(2026, 1, 15)
    assert _parse_date("01/15/2026") == date(2026, 1, 15)
    assert _parse_date("15/01/2026") == date(2026, 1, 15)
    assert _parse_date("20260115") == date(2026, 1, 15)
    assert _parse_date("NOT-A-DATE") is None
    assert _parse_date(None) is None


def test_parse_float_various_formats():
    assert _parse_float(5.0) == 5.0
    assert _parse_float("5.0") == 5.0
    assert _parse_float("$5.00") == 5.0
    assert _parse_float("(5.00)") == -5.0
    assert _parse_float("NOT-A-NUMBER") is None
    assert _parse_float(None) is None
