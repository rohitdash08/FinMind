"""
Secure backup and encrypted export options.
"""
import json
import gzip
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
from ..extensions import db
from ..models import User, Expense, Category, RecurringExpense, Bill


def validate_encryption_key(key: bytes) -> bool:
    """Validate Fernet encryption key format."""
    try:
        Fernet(key)
        return True
    except (ValueError, InvalidToken):
        return False


def create_backup(user_id: int, encryption_key: bytes = None) -> bytes:
    """Create encrypted backup of user data.
    
    Args:
        user_id: User ID to backup
        encryption_key: Optional Fernet encryption key
        
    Returns:
        Compressed and optionally encrypted backup data
        
    Raises:
        ValueError: If encryption key is invalid
    """
    # Validate encryption key if provided
    if encryption_key and not validate_encryption_key(encryption_key):
        raise ValueError("Invalid encryption key format")
    
    # Get user profile
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    data = {
        "version": "1.0",
        "created_at": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "user_profile": {
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "expenses": [],
        "categories": [],
        "recurring": [],
        "bills": [],
    }
    
    # Collect expenses with pagination to avoid OOM
    page_size = 1000
    offset = 0
    while True:
        expenses = Expense.query.filter_by(user_id=user_id)\
            .offset(offset).limit(page_size).all()
        if not expenses:
            break
        for exp in expenses:
            data["expenses"].append({
                "amount": str(exp.amount),
                "currency": exp.currency,
                "type": exp.expense_type,
                "date": exp.spent_at.isoformat(),
                "description": exp.description,
            })
        offset += page_size
    
    # Collect categories
    for cat in Category.query.filter_by(user_id=user_id).all():
        data["categories"].append({
            "name": cat.name,
            "icon": cat.icon,
            "color": cat.color,
        })
    
    # Collect recurring expenses (FIXED: was missing)
    for rec in RecurringExpense.query.filter_by(user_id=user_id).all():
        data["recurring"].append({
            "amount": str(rec.amount),
            "currency": rec.currency,
            "frequency": rec.frequency,
            "description": rec.description,
            "next_date": rec.next_date.isoformat() if rec.next_date else None,
        })
    
    # Collect bills (FIXED: was missing)
    for bill in Bill.query.filter_by(user_id=user_id).all():
        data["bills"].append({
            "name": bill.name,
            "amount": str(bill.amount),
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "paid": bill.paid,
        })
    
    # Compress
    json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
    compressed = gzip.compress(json_data)
    
    # Encrypt if key provided
    if encryption_key:
        f = Fernet(encryption_key)
        return f.encrypt(compressed)
    
    return compressed


def verify_backup(data: bytes, checksum: str) -> bool:
    """Verify backup integrity."""
    return hashlib.sha256(data).hexdigest() == checksum


def get_backup_metadata(data: bytes) -> dict:
    """Get backup metadata without decrypting."""
    try:
        # Try to decompress
        decompressed = gzip.decompress(data)
        # Parse JSON
        json_data = json.loads(decompressed)
        return {
            "version": json_data.get("version"),
            "created_at": json_data.get("created_at"),
            "user_id": json_data.get("user_id"),
            "expense_count": len(json_data.get("expenses", [])),
            "category_count": len(json_data.get("categories", [])),
            "recurring_count": len(json_data.get("recurring", [])),
            "bill_count": len(json_data.get("bills", [])),
        }
    except Exception:
        return {"error": "Unable to parse backup metadata"}
