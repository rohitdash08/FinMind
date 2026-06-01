
"""
Secure backup and encrypted export options.
"""
import json
import gzip
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet
from ..extensions import db
from ..models import User, Expense, Category, RecurringExpense, Bill


def create_backup(user_id: int, encryption_key: bytes = None) -> bytes:
    """Create encrypted backup of user data."""
    data = {
        "version": "1.0",
        "created_at": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "expenses": [],
        "categories": [],
        "recurring": [],
        "bills": [],
    }
    
    # Collect data
    for exp in Expense.query.filter_by(user_id=user_id).all():
        data["expenses"].append({
            "amount": str(exp.amount), "currency": exp.currency,
            "type": exp.expense_type, "date": exp.spent_at.isoformat(),
        })
    
    for cat in Category.query.filter_by(user_id=user_id).all():
        data["categories"].append({"name": cat.name})
    
    # Compress
    json_data = json.dumps(data).encode()
    compressed = gzip.compress(json_data)
    
    # Encrypt if key provided
    if encryption_key:
        f = Fernet(encryption_key)
        return f.encrypt(compressed)
    
    return compressed


def verify_backup(data: bytes, checksum: str) -> bool:
    """Verify backup integrity."""
    return hashlib.sha256(data).hexdigest() == checksum
