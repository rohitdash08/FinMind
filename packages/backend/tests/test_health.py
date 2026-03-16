import app as app_module


def test_health_ready_reports_connected_dependencies(client, monkeypatch):
    monkeypatch.setattr(app_module.db.session, "execute", lambda _query: None)
    monkeypatch.setattr(app_module.redis_client, "ping", lambda: True)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "checks": {"database": "connected", "redis": "connected"},
    }


def test_health_ready_returns_503_when_database_check_fails(client, monkeypatch):
    def fail_database(_query):
        raise RuntimeError("db down")

    monkeypatch.setattr(app_module.db.session, "execute", fail_database)
    monkeypatch.setattr(app_module.redis_client, "ping", lambda: True)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "checks": {"database": "error", "redis": "connected"},
    }


def test_health_ready_returns_503_when_redis_check_fails(client, monkeypatch):
    def fail_redis():
        raise RuntimeError("redis down")

    monkeypatch.setattr(app_module.db.session, "execute", lambda _query: None)
    monkeypatch.setattr(app_module.redis_client, "ping", fail_redis)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "checks": {"database": "connected", "redis": "error"},
    }


def test_health_uses_explicit_cors_origins(client):
    response = client.get("/health", headers={"Origin": "http://localhost:8081"})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_health_sets_default_security_headers(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_schema_compatibility_patch_is_skipped_when_database_is_unreachable(
    app_fixture, monkeypatch, caplog
):
    class FakeEngine:
        class dialect:
            name = "postgresql"

        def raw_connection(self):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        type(app_module.db), "engine", property(lambda _self: FakeEngine())
    )

    with app_fixture.app_context():
        with caplog.at_level("WARNING"):
            app_module._ensure_schema_compatibility(app_fixture)

    assert (
        "Skipping schema compatibility patch until database is reachable" in caplog.text
    )
