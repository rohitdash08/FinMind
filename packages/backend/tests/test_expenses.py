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


def test_expense_import_preview_includes_validation(client, auth_header):
    _create_category(client, auth_header)

    csv_data = (
        "date,amount,description,category_id\n"
        "2026-02-10,10.50,Coffee,\n"
        "2026-03-20,999999.99,Test,\n"
        "X,abc,Bad date,\n"
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
    assert preview["total"] == 3
    assert "warnings" in preview
    assert "summary" in preview
    summary = preview["summary"]
    assert summary["row_count"] == 3
    assert summary["warning_count"] > 0
    assert summary["date_range"] is not None
    assert summary["date_range"]["earliest"] == "2026-02-10"
    amount_warnings = [w for w in preview["warnings"] if w["field"] == "amount"]
    assert len(amount_warnings) >= 1
    date_warnings = [w for w in preview["warnings"] if w["field"] == "date"]
    assert len(date_warnings) >= 1


def test_validate_import_rows_empty():
    from app.services.expense_import import validate_import_rows

    result = validate_import_rows([])
    assert result["summary"]["row_count"] == 0
    assert result["warnings"] == []


def test_validate_import_rows_valid_data():
    from app.services.expense_import import validate_import_rows

    rows = [
        {
            "date": "2026-01-15",
            "amount": 25.00,
            "description": "Groceries",
            "expense_type": "EXPENSE",
        },
        {
            "date": "2026-01-20",
            "amount": 3000.00,
            "description": "Salary",
            "expense_type": "INCOME",
        },
    ]
    result = validate_import_rows(rows)
    assert result["summary"]["row_count"] == 2
    assert result["summary"]["warning_count"] == 0
    assert result["summary"]["income_total"] == 3000.0
    assert result["summary"]["expense_total"] == 25.0


def test_validate_import_rows_flags_issues():
    from app.services.expense_import import validate_import_rows

    rows = [
        {
            "date": "2026-12-31",
            "amount": 500000.00,
            "description": "",
            "expense_type": "EXPENSE",
        },
        {
            "date": "1999-01-01",
            "amount": 10.00,
            "description": "A" * 600,
            "expense_type": "EXPENSE",
        },
    ]
    result = validate_import_rows(rows)
    warnings = result["warnings"]
    row0_warnings = [w for w in warnings if w["row_index"] == 0]
    assert any(w["field"] == "amount" for w in row0_warnings)
    assert any(w["field"] == "description" for w in row0_warnings)
    row1_warnings = [w for w in warnings if w["row_index"] == 1]
    assert any(w["field"] == "date" for w in row1_warnings)
    assert any(w["field"] == "description" for w in row1_warnings)
