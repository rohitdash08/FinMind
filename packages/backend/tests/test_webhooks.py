"""Tests for webhook system (issue #77)."""
import hashlib, hmac, json

def test_sign_payload():
    from app.services.webhooks import sign_payload
    sig = sign_payload("mysecret", b'{"test":1}')
    assert sig.startswith("sha256=")
    assert len(sig) > 10

def test_signature_verification():
    from app.services.webhooks import sign_payload
    payload = b'{"event":"expense.created"}'
    secret = "testsecret123"
    sig = sign_payload(secret, payload)
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert sig == expected

def test_register_webhook_structure():
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        from app.extensions import db
        from app.services.webhooks import WebhookRegistration
        db.create_all()
        from app.services.webhooks import register_webhook
        result = register_webhook(1, "https://example.com/hook", ["expense.created"])
        assert "id" in result
        assert "secret" in result
        assert len(result["secret"]) == 32
