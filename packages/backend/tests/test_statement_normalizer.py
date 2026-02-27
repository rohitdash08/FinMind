"""Tests for universal bank statement normalization."""

import pytest
from app.services.statement_normalizer import (
    normalize_statement, _parse_date, _clean_description,
    _parse_amount, _detect_format, _detect_csv_columns,
)


SAMPLE_CSV = """Date,Description,Amount,Balance
2026-02-01,Grocery Store,-45.50,1954.50
2026-02-02,Salary Deposit,3000.00,4954.50
2026-02-03,Electric Bill,-120.00,4834.50
"""

SAMPLE_CSV_SPLIT = """Transaction Date,Narrative,Debit,Credit,Balance
01/02/2026,Grocery Store,45.50,,1954.50
02/02/2026,Salary Deposit,,3000.00,4954.50
03/02/2026,Electric Bill,120.00,,4834.50
"""

SAMPLE_OFX = """OFXHEADER:100
<OFX>
<BANKMSGSRSV1>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260201
<TRNAMT>-45.50
<NAME>Grocery Store
<FITID>TXN001
</STMTTRN>
<STMTTRN>
<DTPOSTED>20260202
<TRNAMT>3000.00
<NAME>Salary Deposit
<FITID>TXN002
</STMTTRN>
</BANKTRANLIST>
</BANKMSGSRSV1>
</OFX>"""


class TestParseDate:
    def test_iso(self):
        assert _parse_date("2026-02-01") == "2026-02-01"

    def test_dd_mm_yyyy(self):
        assert _parse_date("01/02/2026") == "2026-02-01"

    def test_mm_dd_yyyy(self):
        assert _parse_date("02/01/2026") == "2026-01-02"

    def test_ofx_format(self):
        assert _parse_date("20260201") == "2026-02-01"

    def test_ofx_long(self):
        assert _parse_date("20260201120000") == "2026-02-01"

    def test_invalid(self):
        assert _parse_date("not-a-date") is None


class TestCleanDescription:
    def test_whitespace(self):
        assert _clean_description("  Hello   World  ") == "Hello World"

    def test_card_mask(self):
        assert "****" not in _clean_description("VISA 4532****1234 Purchase")


class TestParseAmount:
    def test_simple(self):
        assert _parse_amount("45.50") == 45.50

    def test_negative(self):
        assert _parse_amount("-120.00") == -120.00

    def test_comma(self):
        assert _parse_amount("1,234.56") == 1234.56

    def test_empty(self):
        assert _parse_amount("") == 0.0


class TestDetectFormat:
    def test_csv(self):
        assert _detect_format("Date,Amount\n2026-01-01,100") == "csv"

    def test_ofx(self):
        assert _detect_format("OFXHEADER:100\n<OFX>") == "ofx"


class TestDetectColumns:
    def test_standard(self):
        m = _detect_csv_columns(["Date", "Description", "Amount", "Balance"])
        assert m["date"] == 0
        assert m["description"] == 1
        assert m["amount"] == 2
        assert m["balance"] == 3

    def test_split_debit_credit(self):
        m = _detect_csv_columns(["Transaction Date", "Narrative", "Debit", "Credit"])
        assert "debit" in m
        assert "credit" in m


class TestNormalizeCSV:
    def test_basic(self):
        result = normalize_statement(SAMPLE_CSV)
        assert result["format_detected"] == "csv"
        assert result["total_transactions"] == 3
        txns = result["transactions"]
        assert txns[0]["date"] == "2026-02-01"
        assert txns[0]["amount"] == 45.50
        assert txns[0]["transaction_type"] == "debit"
        assert txns[1]["transaction_type"] == "credit"

    def test_split_columns(self):
        result = normalize_statement(SAMPLE_CSV_SPLIT)
        assert result["total_transactions"] == 3

    def test_summary(self):
        result = normalize_statement(SAMPLE_CSV)
        s = result["summary"]
        assert s["total_debits"] > 0
        assert s["total_credits"] > 0
        assert s["date_range"]["start"] == "2026-02-01"

    def test_empty(self):
        result = normalize_statement("Date,Amount\n")
        assert result["total_transactions"] == 0

    def test_bad_rows(self):
        csv_data = "Date,Amount\n2026-01-01,100\nbaddate,200\n"
        result = normalize_statement(csv_data)
        assert len(result["warnings"]) > 0


class TestNormalizeOFX:
    def test_basic(self):
        result = normalize_statement(SAMPLE_OFX)
        assert result["format_detected"] == "ofx"
        assert result["total_transactions"] == 2
        txns = result["transactions"]
        assert txns[0]["amount"] == 45.50
        assert txns[0]["transaction_type"] == "debit"
        assert txns[0]["reference"] == "TXN001"
        assert txns[1]["transaction_type"] == "credit"

    def test_format_hint(self):
        result = normalize_statement(SAMPLE_OFX, format_hint="ofx")
        assert result["format_detected"] == "ofx"


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def token(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        from flask_jwt_extended import create_access_token
        u = User(email="t@t.com", password_hash=generate_password_hash("p"))
        db.session.add(u)
        db.session.commit()
        return create_access_token(identity=str(u.id))


class TestAPI:
    def test_normalize_endpoint(self, app, token):
        client = app.test_client()
        resp = client.post(
            "/statements/normalize",
            json={"content": SAMPLE_CSV},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["total_transactions"] == 3

    def test_preview_endpoint(self, app, token):
        client = app.test_client()
        resp = client.post(
            "/statements/preview",
            json={"content": SAMPLE_CSV},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["preview"] is True

    def test_missing_content(self, app, token):
        client = app.test_client()
        resp = client.post(
            "/statements/normalize",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
