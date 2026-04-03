import pytest
from app.services.payee_alias import PayeeAliasService, _payee_aliases

@pytest.fixture(autouse=True)
def clear_data():
    _payee_aliases.clear()
    yield
    _payee_aliases.clear()

@pytest.fixture
def svc():
    return PayeeAliasService()

def test_normalize_amazon(svc):
    assert svc.normalize("AMZN*MKTP US") == "Amazon"

def test_normalize_netflix(svc):
    assert svc.normalize("NETFLIX.COM") == "Netflix"

def test_normalize_starbucks(svc):
    assert svc.normalize("STARBUCKS STORE 12345") == "Starbucks"

def test_normalize_unknown_title_cases(svc):
    result = svc.normalize("local bakery")
    assert result == "Local Bakery"

def test_set_and_get_alias(svc):
    svc.set_alias("user1", "AMZN*MKTP US", "My Amazon")
    result = svc.get_alias("user1", "AMZN*MKTP US")
    assert result == "My Amazon"

def test_delete_alias(svc):
    svc.set_alias("user2", "NETFLIX.COM", "Streaming")
    success = svc.delete_alias("user2", "Netflix")
    assert success is True
    result = svc.get_alias("user2", "NETFLIX.COM")
    assert result == "Netflix"  # Falls back to auto-normalized

def test_bulk_normalize(svc):
    raw_names = ["AMZN*MKTP US", "NETFLIX.COM", "unknown store"]
    results = svc.bulk_normalize("user3", raw_names)
    display_map = {r["raw"]: r["display"] for r in results}
    assert display_map["AMZN*MKTP US"] == "Amazon"
    assert display_map["NETFLIX.COM"] == "Netflix"

def test_suggest_aliases(svc):
    raw_names = ["AMZN*MKTP US", "NETFLIX.COM", "local bakery"]
    suggestions = svc.suggest_aliases("user4", raw_names)
    suggested_raws = [s["raw"] for s in suggestions]
    assert "AMZN*MKTP US" in suggested_raws
    assert "NETFLIX.COM" in suggested_raws

def test_list_aliases(svc):
    svc.set_alias("user5", "AMZN*MKTP US", "Shopping")
    svc.set_alias("user5", "NETFLIX.COM", "Movies")
    aliases = svc.list_aliases("user5")
    assert len(aliases) == 2