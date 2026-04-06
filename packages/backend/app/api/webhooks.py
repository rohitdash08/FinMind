from fastapi import APIRouter
from typing import List
import requests
import secrets

router = APIRouter(prefix="/webhooks")

class WebhookManager:
    def __init__(self):
        self.webhooks = {}
    
    def register(self, user_id: str, url: str, events: List[str]):
        webhook_id = secrets.token_hex(16)
        self.webhooks[webhook_id] = {
            "user_id": user_id,
            "url": url,
            "events": events,
            "secret": secrets.token_hex(32)
        }
        return webhook_id
    
    def dispatch(self, event_type: str, data: dict):
        for webhook in self.webhooks.values():
            if event_type in webhook["events"]:
                try:
                    requests.post(webhook["url"], json={"event": event_type, "data": data}, timeout=5)
                except:
                    pass

webhook_manager = WebhookManager()

@router.post("/register")
async def register_webhook(url: str, events: List[str], user_id: str):
    webhook_id = webhook_manager.register(user_id, url, events)
    return {"webhook_id": webhook_id, "status": "active"}

@router.post("/events")
async def send_event(event_type: str, data: dict):
    webhook_manager.dispatch(event_type, data)
    return {"status": "dispatched"}
