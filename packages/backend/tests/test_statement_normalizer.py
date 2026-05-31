from io import BytesIO


def test_list_adapters(client, auth_header):
    r = client.get("/statement-normalizer/adapters", headers=auth_header)
    assert r.status_code == 200
    adapters = r.get_json()
    assert len(adapters) >= 3
    names = [a["name"] for a in adapters]
    assert "CSV Generic" in names
    assert "OFX Standard" in names
    assert "QIF Standard" in names


def test_register_adapter(client, auth_header):
    payload = {
        "name": "MyCustomBank CSV",
        "format": "CSV",
        "schema_map": {
            "date": {"field": "txn_date", "fallback": []},
            "amount": {"field": "txn_amount", "fallback": []},
            "description": {"field": "memo", "fallback": []},
        },
    }
    r = client.post("/statement-normalizer/adapters", json=payload, headers=auth_header)
    assert r.status_code == 201
    result = r.get_json()
    assert result["key"] == "mycustombank_csv"


def test_csv_preview_and_commit(client, auth_header):
    csv_data = (
        "date,amount,description\n"
        "2026-06-01,50.00,Groceries\n"
        "2026-06-02,25.00,Gas\n"
    )
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "statement.csv")}
    r = client.post(
        "/statement-normalizer/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    preview = r.get_json()
    assert preview["total"] == 2
    assert preview["detected_format"] == "CSV"
    assert preview["adapter"] == "CSV Generic"

    r = client.post(
        "/statement-normalizer/commit",
        json={"transactions": preview["transactions"]},
        headers=auth_header,
    )
    assert r.status_code == 201
    result = r.get_json()
    assert result["inserted"] == 2
    assert result["duplicates"] == 0

    r = client.post(
        "/statement-normalizer/commit",
        json={"transactions": preview["transactions"]},
        headers=auth_header,
    )
    assert r.status_code == 201
    result2 = r.get_json()
    assert result2["inserted"] == 0
    assert result2["duplicates"] == 2


def test_qif_preview(client, auth_header):
    qif_data = (
        "!Type:Bank\n"
        "D2026-06-01\n"
        "T-150.00\n"
        "PElectric Bill\n"
        "^\n"
        "D2026-06-05\n"
        "T2000.00\n"
        "PSalary\n"
        "^\n"
    )
    data = {"file": (BytesIO(qif_data.encode("utf-8")), "statement.qif")}
    r = client.post(
        "/statement-normalizer/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    preview = r.get_json()
    assert preview["total"] == 2
    assert preview["detected_format"] == "QIF"


def test_ofx_preview(client, auth_header):
    ofx_data = (
        "OFXHEADER:100\n"
        "<OFX>\n"
        "<BANKTRANLIST>\n"
        "<STMTTRN>\n"
        "<TRNTYPE>DEBIT\n"
        "<DTPOSTED>20260601\n"
        "<TRNAMT>-75.00\n"
        "<NAME>Restaurant\n"
        "</STMTTRN>\n"
        "</BANKTRANLIST>\n"
        "</OFX>\n"
    )
    data = {"file": (BytesIO(ofx_data.encode("utf-8")), "statement.ofx")}
    r = client.post(
        "/statement-normalizer/preview",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    preview = r.get_json()
    assert preview["total"] == 1
    assert preview["detected_format"] == "OFX"
    assert preview["transactions"][0]["description"] == "Restaurant"
