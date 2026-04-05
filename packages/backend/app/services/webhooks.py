"""Webhook event system (issue #77)."""
import hashlib, hmac, json, logging, time, uuid
import requests
from ..extensions import db, redis_client

logger = logging.getLogger("finmind.webhooks")
QUEUE_KEY = "webhooks:queue"
REG_PREFIX = "webhooks:reg:"
TTL = 60 * 60 * 24 * 30


class WebhookRegistration(db.Model):
    __tablename__ = "webhook_registrations"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(64), nullable=False)
    events = db.Column(db.String(500), default="*")  # comma-sep event types or *
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)


def register_webhook(user_id: int, url: str, events: list = None) -> dict:
    secret = hmac.new(str(uuid.uuid4()).encode(), digestmod=hashlib.sha256).hexdigest()[:32]
    wh = WebhookRegistration(user_id=user_id, url=url,
                              secret=secret, events=",".join(events) if events else "*")
    db.session.add(wh); db.session.commit()
    return {"id": wh.id, "url": url, "secret": secret, "events": events or ["*"]}


def sign_payload(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def deliver_webhook(webhook_id: str, event_type: str, payload: dict):
    wh = db.session.get(WebhookRegistration, webhook_id)
    if not wh or not wh.active: return
    if wh.events != "*" and event_type not in wh.events.split(","):
        return
    body = json.dumps({"event": event_type, "ts": time.time(), "data": payload}).encode()
    sig = sign_payload(wh.secret, body)
    try:
        resp = requests.post(wh.url, data=body, headers={
            "Content-Type": "application/json",
            "X-FinMind-Signature": sig,
            "X-FinMind-Event": event_type,
        }, timeout=5)
        logger.info("Webhook %s delivered event=%s status=%d", webhook_id, event_type, resp.status_code)
    except Exception as e:
        logger.warning("Webhook %s delivery failed: %s", webhook_id, e)
