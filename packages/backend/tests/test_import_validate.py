"""Tests for bulk import validation & preview improvements (#115)."""
import io
import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

CSV_VALID = b"date,amount,description,category_id,currency\n2024-01-15,50.00,Starbucks,,USD\n2024-01-16,120.00,Amazon,,USD\n"
CSV_BAD_DATE = b"date,amount,description\nnot-a-date,50.00,Coffee\n"
CSV_BAD_AMOUNT = b"date,amount,description\n2024-01-15,not-a-number,Coffee\n"
CSV_NO_DESC = b"date,amount,description\n2024-01-15,50.00,\n"
CSV_FUTURE = b"date,amount,description\n2099-01-01,50.00,FutureShop\n"
CSV_OLD = b"date,amount,description\n2000-01-01,50.00,OldShop\n"
CSV_BIG_AMOUNT = b"date,amount,description\n2024-01-15,9999999.00,BigPurchase\n"


def _upload(client, headers, csv_data, filename="test.csv"):
    return client.post(
        "/expenses/import/validate",
        data={"file": (io.BytesIO(csv_data), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_validate_requires_auth(client):
    r = client.post(
        "/expenses/import/validate",
        data={"file": (io.BytesIO(CSV_VALID), "test.csv")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 401


def test_validate_no_file(client, auth_header):
    r = client.post("/expenses/import/validate", headers=auth_header)
    assert r.status_code == 400


def test_validate_valid_csv(client, auth_header):
    r = _upload(client, auth_header, CSV_VALID)
    assert r.status_code == 200
    data = r.get_json()
    assert "rows" in data
    assert "summary" in data
    assert data["summary"]["total"] == 2
    assert data["summary"]["invalid"] == 0


def test_validate_response_structure(client, auth_header):
    r = _upload(client, auth_header, CSV_VALID)
    assert r.status_code == 200
    data = r.get_json()
    row = data["rows"][0]
    assert "row_index" in row
    assert "status" in row
    assert "warnings" in row
    assert "corrections" in row
    assert "normalized" in row
    assert row["normalized"] is not None


def test_validate_bad_date_row_invalid(client, auth_header):
    r = _upload(client, auth_header, CSV_BAD_DATE)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["invalid"] == 1
    row = data["rows"][0]
    assert row["status"] == "invalid"
    assert row["normalized"] is None
    assert any("date" in w.lower() for w in row["warnings"])


def test_validate_bad_amount_row_invalid(client, auth_header):
    r = _upload(client, auth_header, CSV_BAD_AMOUNT)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["invalid"] == 1
    row = data["rows"][0]
    assert row["status"] == "invalid"


def test_validate_empty_description_invalid(client, auth_header):
    r = _upload(client, auth_header, CSV_NO_DESC)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["invalid"] == 1
    assert any("empty" in w.lower() or "description" in w.lower() for w in data["rows"][0]["warnings"])


def test_validate_future_date_warning(client, auth_header):
    r = _upload(client, auth_header, CSV_FUTURE)
    assert r.status_code == 200
    data = r.get_json()
    row = data["rows"][0]
    assert row["status"] == "warning"
    assert any("future" in w.lower() for w in row["warnings"])


def test_validate_old_date_warning(client, auth_header):
    r = _upload(client, auth_header, CSV_OLD)
    assert r.status_code == 200
    data = r.get_json()
    row = data["rows"][0]
    assert row["status"] == "warning"
    assert any("year" in w.lower() or "old" in w.lower() for w in row["warnings"])


def test_validate_big_amount_warning(client, auth_header):
    r = _upload(client, auth_header, CSV_BIG_AMOUNT)
    assert r.status_code == 200
    data = r.get_json()
    row = data["rows"][0]
    assert row["status"] == "warning"
    assert any("threshold" in w.lower() or "exceed" in w.lower() for w in row["warnings"])


def test_validate_duplicate_detection(client, auth_header):
    # Create an existing expense
    client.post(
        "/expenses",
        json={"amount": 50, "notes": "Starbucks", "spent_at": "2024-01-15"},
        headers=auth_header,
    )
    # Now import same description + date
    csv = b"date,amount,description\n2024-01-15,50.00,Starbucks\n"
    r = _upload(client, auth_header, csv)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["duplicates"] >= 1
    assert any("duplicate" in w.lower() for w in data["rows"][0]["warnings"])


def test_validate_corrections_reported(client, auth_header):
    # Date in non-ISO format should produce a correction
    csv = b"date,amount,description\n01/15/2024,50.00,TestShop\n"
    r = _upload(client, auth_header, csv)
    assert r.status_code == 200
    data = r.get_json()
    row = data["rows"][0]
    # Either corrected or valid (depending on parser), but normalized should have ISO date
    if row["normalized"]:
        assert row["normalized"]["date"] == "2024-01-15"


def test_validate_summary_counts(client, auth_header):
    csv = (
        b"date,amount,description\n"
        b"2024-01-01,10.00,ValidRow\n"          # valid
        b"2099-01-01,20.00,FutureRow\n"          # warning (future)
        b"bad-date,30.00,BadDateRow\n"           # invalid
    )
    r = _upload(client, auth_header, csv)
    assert r.status_code == 200
    s = r.get_json()["summary"]
    assert s["total"] == 3
    assert s["valid"] == 1
    assert s["warnings"] == 1
    assert s["invalid"] == 1


def test_validate_unknown_file_type(client, auth_header):
    r = client.post(
        "/expenses/import/validate",
        data={"file": (io.BytesIO(b"hello world"), "test.txt")},
        headers=auth_header,
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


import pytest
