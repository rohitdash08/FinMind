"""Tests for bulk import validation & preview."""

import json
import pytest
from datetime import date, timedelta
from app.extensions import db
from app.models import Category, Expense


def _create_category(client, name="Food"):
    with client.application.app_context():
        cat = Category(name=name, user_id=1)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — parsing
# ═══════════════════════════════════════════════════════════════════


class TestParsing:
    def test_parse_csv(self, client, auth_header):
        from app.services.bulk_import import parse_csv

        rows = parse_csv("amount,date,notes\n50,2025-01-01,Lunch\n100,2025-01-02,Dinner\n")
        assert len(rows) == 2
        assert rows[0]["amount"] == "50"

    def test_parse_json(self, client, auth_header):
        from app.services.bulk_import import parse_json

        rows = parse_json('[{"amount": "50", "date": "2025-01-01"}]')
        assert len(rows) == 1

    def test_parse_json_transactions_key(self, client, auth_header):
        from app.services.bulk_import import parse_json

        rows = parse_json('{"transactions": [{"amount": "100"}]}')
        assert len(rows) == 1

    def test_parse_json_expenses_key(self, client, auth_header):
        from app.services.bulk_import import parse_json

        rows = parse_json('{"expenses": [{"amount": "200"}]}')
        assert len(rows) == 1

    def test_detect_format_csv(self, client, auth_header):
        from app.services.bulk_import import detect_format

        assert detect_format("amount,date\n50,2025-01-01", "data.csv") == "csv"
        assert detect_format("amount,date\n50,2025-01-01") == "csv"

    def test_detect_format_json(self, client, auth_header):
        from app.services.bulk_import import detect_format

        assert detect_format("[{}]", "data.json") == "json"
        assert detect_format('[{"amount": 50}]') == "json"


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — validation
# ═══════════════════════════════════════════════════════════════════


class TestValidation:
    def test_valid_csv(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,date,notes\n50.00,2025-01-15,Lunch\n100.00,2025-02-01,Groceries\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["format"] == "csv"
        assert result["total_rows"] == 2
        assert result["valid_rows"] == 2
        assert result["invalid_rows"] == 0
        assert result["summary"]["total_amount"] == 150.0

    def test_valid_json(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = json.dumps([
            {"amount": "75.50", "date": "2025-03-01", "notes": "Coffee"},
        ])
        with client.application.app_context():
            result = validate_and_preview(1, content, file_format="json")

        assert result["format"] == "json"
        assert result["valid_rows"] == 1

    def test_missing_amount_column(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "date,notes\n2025-01-01,Lunch\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 0
        assert any("amount" in e.lower() for e in result["errors"])

    def test_invalid_amount(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,date\nabc,2025-01-01\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["invalid_rows"] == 1

    def test_currency_symbol_cleanup(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,date\n$50.00,2025-01-01\n₹1000,2025-01-02\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 2
        assert result["rows"][0]["parsed"]["amount"] == 50.0
        assert result["rows"][1]["parsed"]["amount"] == 1000.0

    def test_date_format_detection(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,date\n50,03/15/2025\n100,15-03-2025\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 2

    def test_missing_date_defaults_to_today(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,notes\n50,Lunch\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 1
        assert result["rows"][0]["parsed"]["date"] == str(date.today())

    def test_category_matching(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        cat_id = _create_category(client, "Food")
        content = "amount,category\n50,Food\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["rows"][0]["parsed"]["category_id"] == cat_id

    def test_unknown_category_warning(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,category\n50,Electronics\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 1
        assert any("Electronics" in w for w in result["warnings"])

    def test_field_aliases(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "total,transaction_date,memo\n50,2025-01-01,Lunch\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["valid_rows"] == 1
        assert result["field_mapping"]["total"] == "amount"
        assert result["field_mapping"]["transaction_date"] == "date"
        assert result["field_mapping"]["memo"] == "notes"

    def test_empty_content(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        content = "amount,date\n"
        with client.application.app_context():
            result = validate_and_preview(1, content)

        assert result["total_rows"] == 0
        assert "no data" in result["warnings"][0].lower()

    def test_malformed_csv(self, client, auth_header):
        from app.services.bulk_import import validate_and_preview

        with client.application.app_context():
            result = validate_and_preview(1, "", file_format="json")

        assert len(result["errors"]) > 0


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — execute import
# ═══════════════════════════════════════════════════════════════════


class TestExecuteImport:
    def test_basic_import(self, client, auth_header):
        from app.services.bulk_import import execute_import

        content = "amount,date,notes\n50.00,2025-01-15,Lunch\n100.00,2025-02-01,Groceries\n"
        with client.application.app_context():
            result = execute_import(1, content)

        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["total_amount"] == 150.0

        with client.application.app_context():
            expenses = Expense.query.filter_by(user_id=1).all()
            assert len(expenses) == 2

    def test_auto_create_categories(self, client, auth_header):
        from app.services.bulk_import import execute_import

        content = "amount,category\n50,NewCategory\n100,NewCategory\n"
        with client.application.app_context():
            result = execute_import(1, content, create_categories=True)

        assert result["imported"] == 2
        assert "NewCategory" in result["categories_created"]
        assert len(result["categories_created"]) == 1  # Deduped

    def test_skip_invalid_rows(self, client, auth_header):
        from app.services.bulk_import import execute_import

        content = "amount,date\n50,2025-01-01\nbad,2025-01-02\n100,2025-01-03\n"
        with client.application.app_context():
            result = execute_import(1, content, skip_invalid=True)

        assert result["imported"] == 2
        assert result["skipped"] == 1

    def test_fail_on_invalid(self, client, auth_header):
        from app.services.bulk_import import execute_import

        content = "amount,date\nbad,2025-01-01\n"
        with client.application.app_context():
            result = execute_import(1, content, skip_invalid=False)

        assert result["imported"] == 0

    def test_json_import(self, client, auth_header):
        from app.services.bulk_import import execute_import

        content = json.dumps([
            {"amount": "75", "date": "2025-03-01", "notes": "Coffee"},
            {"amount": "200", "date": "2025-03-02", "notes": "Dinner"},
        ])
        with client.application.app_context():
            result = execute_import(1, content, file_format="json")

        assert result["imported"] == 2
        assert result["total_amount"] == 275.0


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — template
# ═══════════════════════════════════════════════════════════════════


class TestTemplate:
    def test_csv_template(self, client, auth_header):
        from app.services.bulk_import import get_import_template

        template = get_import_template("csv")
        assert "amount" in template
        assert "date" in template

    def test_json_template(self, client, auth_header):
        from app.services.bulk_import import get_import_template

        template = get_import_template("json")
        data = json.loads(template)
        assert "transactions" in data


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestImportRoutes:
    # ── POST /import/preview ──
    def test_preview_csv(self, client, auth_header):
        r = client.post(
            "/import/preview",
            headers=auth_header,
            json={"content": "amount,date,notes\n50,2025-01-01,Lunch\n"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["valid_rows"] == 1
        assert "summary" in body

    def test_preview_json(self, client, auth_header):
        r = client.post(
            "/import/preview",
            headers=auth_header,
            json={
                "content": json.dumps([{"amount": "50", "date": "2025-01-01"}]),
                "format": "json",
            },
        )
        assert r.status_code == 200
        assert r.get_json()["valid_rows"] == 1

    def test_preview_missing_content(self, client, auth_header):
        r = client.post("/import/preview", headers=auth_header, json={})
        assert r.status_code == 400

    def test_preview_unauthorized(self, client):
        r = client.post("/import/preview", json={"content": "amount\n50\n"})
        assert r.status_code == 401

    # ── POST /import/execute ──
    def test_execute_csv(self, client, auth_header):
        r = client.post(
            "/import/execute",
            headers=auth_header,
            json={"content": "amount,date,notes\n50,2025-01-01,Lunch\n100,2025-01-02,Dinner\n"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["imported"] == 2

    def test_execute_missing_content(self, client, auth_header):
        r = client.post("/import/execute", headers=auth_header, json={})
        assert r.status_code == 400

    def test_execute_unauthorized(self, client):
        r = client.post("/import/execute", json={"content": "amount\n50\n"})
        assert r.status_code == 401

    # ── GET /import/template ──
    def test_template_csv(self, client, auth_header):
        r = client.get("/import/template", headers=auth_header)
        assert r.status_code == 200
        assert "amount" in r.get_data(as_text=True)

    def test_template_json(self, client, auth_header):
        r = client.get("/import/template?format=json", headers=auth_header)
        assert r.status_code == 200
        data = json.loads(r.get_data(as_text=True))
        assert "transactions" in data

    def test_template_unauthorized(self, client):
        r = client.get("/import/template")
        assert r.status_code == 401
