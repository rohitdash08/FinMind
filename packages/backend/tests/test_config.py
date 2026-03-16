from app.config import Settings


def test_cors_origins_include_container_frontend_origin():
    cfg = Settings()

    assert "http://frontend" in cfg.cors_origins
    assert "http://frontend:80" in cfg.cors_origins
