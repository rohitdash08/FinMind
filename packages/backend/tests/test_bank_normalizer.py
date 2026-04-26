"""Tests for universal bank statement normalization (#112)."""

import io


def _make_file(client, auth_header, content, filename, content_type="text/csv"):
    return client.post(
        "/expenses/import/normalize",
        data={"file": (io.BytesIO(content.encode()), filename, content_type)},
        headers=auth_header,
        content_type="multipart/form-data",
    )


class TestBankStatementNormalization:
    def test_generic_csv(self, client, auth_header):
        csv_data = (
            "date,amount,description,currency\n"
            "2024-01-15,25.00,Coffee Shop,USD\n"
            "2024-01-20,150.00,Grocery Store,USD\n"
        )
        r = _make_file(client, auth_header, csv_data, "statement.csv")
        assert r.status_code == 200
        data = r.get_json()
        assert data["format_detected"] == "CSV"
        assert data["total_transactions"] == 2
        assert len(data["transactions"]) == 2
        assert len(data["duplicate_fingerprints"]) == 2

    def test_chase_csv_profile_detection(self, client, auth_header):
        csv_data = (
            "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
            "01/15/2024,01/16/2024,STARBUCKS,Food & Drink,Sale,-4.50,\n"
            "01/20/2024,01/21/2024,AMAZON.COM,Shopping,Sale,-35.99,\n"
        )
        r = _make_file(client, auth_header, csv_data, "chase.csv")
        assert r.status_code == 200
        data = r.get_json()
        assert data["bank_profile"] == "Chase"
        assert data["total_transactions"] == 2

    def test_ofx_format(self, client, auth_header):
        ofx_data = (
            "OFXHEADER:100\n"
            "DATA:OFXSGML\n"
            "<OFX>\n"
            "<BANKMSGSRSV1>\n"
            "<STMTTRNRS>\n"
            "<BANKTRANLIST>\n"
            "<STMTTRN>\n"
            "<DTPOSTED>20240115120000\n"
            "<TRNAMT>-25.00\n"
            "<MEMO>Coffee Shop\n"
            "</STMTTRN>\n"
            "<STMTTRN>\n"
            "<DTPOSTED>20240120\n"
            "<TRNAMT>-150.00\n"
            "<MEMO>Grocery Store\n"
            "</STMTTRN>\n"
            "</BANKTRANLIST>\n"
            "</STMTTRNRS>\n"
            "</BANKMSGSRSV1>\n"
            "</OFX>\n"
        )
        r = _make_file(client, auth_header, ofx_data, "statement.ofx", "application/ofx")
        assert r.status_code == 200
        data = r.get_json()
        assert data["format_detected"] == "OFX/QFX"
        assert data["total_transactions"] >= 1

    def test_qif_format(self, client, auth_header):
        qif_data = (
            "!Type:Bank\n"
            "D01/15/2024\n"
            "T-25.00\n"
            "PStarbucks Coffee\n"
            "^\n"
            "D01/20/2024\n"
            "T-150.00\n"
            "PGrocery Mart\n"
            "^\n"
        )
        r = _make_file(client, auth_header, qif_data, "statement.qif", "application/qif")
        assert r.status_code == 200
        data = r.get_json()
        assert data["format_detected"] == "QIF"
        assert data["total_transactions"] >= 1

    def test_unsupported_format_returns_400(self, client, auth_header):
        r = _make_file(client, auth_header, "<root/>", "statement.xml", "application/xml")
        assert r.status_code == 400

    def test_no_file_returns_400(self, client, auth_header):
        r = client.post(
            "/expenses/import/normalize",
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_duplicate_fingerprints_are_deterministic(self, client, auth_header):
        csv_data = (
            "date,amount,description,currency\n"
            "2024-01-15,25.00,Coffee Shop,USD\n"
        )
        r1 = _make_file(client, auth_header, csv_data, "s1.csv")
        r2 = _make_file(client, auth_header, csv_data, "s2.csv")
        assert r1.get_json()["duplicate_fingerprints"] == r2.get_json()["duplicate_fingerprints"]

    def test_requires_auth(self, client):
        r = client.post("/expenses/import/normalize")
        assert r.status_code == 401
