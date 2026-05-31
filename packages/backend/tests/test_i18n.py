def test_list_locales(client):
    r = client.get("/i18n/locales")
    assert r.status_code == 200
    locales = r.get_json()
    assert "en-US" in locales
    assert "de-DE" in locales


def test_locale_info(client):
    r = client.get("/i18n/locale?locale=de-DE")
    assert r.status_code == 200
    info = r.get_json()
    assert info["currency"]["symbol"] == "\u20ac"
    assert info["number"]["decimal"] == ","


def test_format_currency(client):
    r = client.post("/i18n/format/currency", json={"amount": 1234.56, "locale": "en-US"})
    assert r.status_code == 200
    assert r.get_json()["formatted"] == "$1,234.56"

    r = client.post("/i18n/format/currency", json={"amount": 1234.56, "locale": "de-DE"})
    assert r.status_code == 200
    assert r.get_json()["formatted"] == "\u20ac1.234,56"


def test_format_date(client):
    r = client.post(
        "/i18n/format/date", json={"date": "2026-02-10", "locale": "en-US", "style": "short"}
    )
    assert r.status_code == 200
    assert r.get_json()["formatted"] == "02/10/2026"


def test_format_number(client):
    r = client.post(
        "/i18n/format/number", json={"value": 1234567.89, "locale": "en-US", "decimals": 2}
    )
    assert r.status_code == 200
    assert r.get_json()["formatted"] == "1,234,567.89"


def test_detect_locale(client):
    r = client.post(
        "/i18n/detect",
        json={"accept_language": "de-DE,en-US;q=0.9"},
    )
    assert r.status_code == 200
    assert r.get_json()["locale"] == "de-DE"

    r = client.post("/i18n/detect", json={})
    assert r.status_code == 200
    assert r.get_json()["locale"] == "en-US"
