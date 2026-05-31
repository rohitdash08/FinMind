from io import BytesIO


def test_validate_valid_csv(client, auth_header):
    csv_data = "date,amount,description\n2026-02-10,10.50,Coffee\n2026-02-11,22.00,Lunch\n"
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "test.csv")}
    r = client.post(
        "/import-validation/validate-csv",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    result = r.get_json()
    assert result["total"] == 2
    assert result["valid"] == 2
    assert result["with_errors"] == 0


def test_validate_invalid_csv(client, auth_header):
    csv_data = "date,amount,description\nnot-a-date,invalid-amount,\n"
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "test.csv")}
    r = client.post(
        "/import-validation/validate-csv",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    result = r.get_json()
    assert result["valid"] == 0
    assert result["with_errors"] >= 1


def test_detect_format(client, auth_header):
    csv_data = "Transaction Date,Amount,Description\n2026-02-10,10.50,Coffee\n"
    data = {"file": (BytesIO(csv_data.encode("utf-8")), "test.csv")}
    r = client.post(
        "/import-validation/detect-format",
        data=data,
        content_type="multipart/form-data",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["detected_format"] == "chase"


def test_list_formats(client, auth_header):
    r = client.get("/import-validation/formats", headers=auth_header)
    assert r.status_code == 200
    formats = r.get_json()
    assert "chase" in formats
    assert "hdfc" in formats
