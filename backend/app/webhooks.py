from flask_webhook import Webhook
from backend.app import db
from backend.app.models import User, Expense, Bill
from backend.app.config import WEBHOOK_SECRET, WEBHOOK_PRIVATE_KEY
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import json

def sign_payload(payload):
    payload_json = json.dumps(payload).encode()
    signature = WEBHOOK_PRIVATE_KEY.sign(
        payload_json,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return signature

def register_webhooks(webhook):
    @webhook.hook('user.created')
    def user_created(user_id):
        user = User.query.get(user_id)
        payload = {'user_id': user.id, 'email': user.email}
        signature = sign_payload(payload)
        return {'payload': payload, 'signature': signature.hex()}

    @webhook.hook('expense.created')
    def expense_created(expense_id):
        expense = Expense.query.get(expense_id)
        payload = {'expense_id': expense.id, 'amount': expense.amount, 'category': expense.category}
        signature = sign_payload(payload)
        return {'payload': payload, 'signature': signature.hex()}

    @webhook.hook('bill.created')
    def bill_created(bill_id):
        bill = Bill.query.get(bill_id)
        payload = {'bill_id': bill.id, 'amount': bill.amount, 'due_date': bill.due_date.isoformat()}
        signature = sign_payload(payload)
        return {'payload': payload, 'signature': signature.hex()}