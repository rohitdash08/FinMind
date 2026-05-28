"""Receipt Scanner & OCR Parser.

Digital receipt management:
- Receipt parsing (simulated OCR for text extraction)
- Store, merchant, amount, date extraction
- Line-item parsing with categories
- Receipt storage and search
- Duplicate detection
- Expense auto-categorization from receipts
- Export to CSV/JSON
"""

import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.receipt")


class ReceiptItem:
    def __init__(self, name: str, quantity: float, unit_price: float,
                 total: float = None, category: str = ""):
        self.name = name
        self.quantity = quantity
        self.unit_price = unit_price
        self.total = total or (quantity * unit_price)
        self.category = category

    def to_dict(self):
        return {
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": round(self.unit_price, 2),
            "total": round(self.total, 2),
            "category": self.category,
        }


class Receipt:
    def __init__(self, receipt_id: str, store: str, total: float,
                 date: str, items: list = None, raw_text: str = "",
                 category: str = "", payment_method: str = "",
                 tax: float = 0, tip: float = 0):
        self.receipt_id = receipt_id
        self.store = store
        self.total = total
        self.date = date
        self.items = items or []
        self.raw_text = raw_text
        self.category = category
        self.payment_method = payment_method
        self.tax = tax
        self.tip = tip
        self.created_at = datetime.utcnow().isoformat()

    @property
    def subtotal(self) -> float:
        return sum(i.total for i in self.items) if self.items else self.total - self.tax - self.tip

    @property
    def content_hash(self) -> str:
        """Hash for duplicate detection."""
        content = f"{self.store}:{self.total}:{self.date}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def to_dict(self):
        return {
            "receipt_id": self.receipt_id,
            "store": self.store,
            "total": round(self.total, 2),
            "subtotal": round(self.subtotal, 2),
            "tax": round(self.tax, 2),
            "tip": round(self.tip, 2),
            "date": self.date,
            "items": [i.to_dict() for i in self.items],
            "category": self.category,
            "payment_method": self.payment_method,
            "item_count": len(self.items),
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }


class ReceiptScannerService:
    """Scan, parse, and manage receipts."""

    # Common store name patterns
    STORE_PATTERNS = [
        (r"wall?mart|walmart", "Walmart"),
        (r"target", "Target"),
        (r"costco", "Costco"),
        (r"whole\s?foods", "Whole Foods"),
        (r"amazon", "Amazon"),
        (r"starbucks", "Starbucks"),
        (r"mcdonald|mc\s?donald", "McDonalds"),
        (r"uber|lyft", "Ride-share"),
        (r"netflix|spotify|hulu", "Subscription"),
    ]

    # Category keywords
    CATEGORY_KEYWORDS = {
        "groceries": ["milk", "bread", "eggs", "produce", "fruit", "vegetable",
                       "meat", "cheese", "yogurt", "cereal", "rice", "pasta"],
        "dining": ["coffee", "latte", "sandwich", "burger", "pizza", "sushi",
                    "restaurant", "cafe", "dine"],
        "transportation": ["gas", "fuel", "uber", "lyft", "parking", "toll",
                           "transit", "bus", "train", "metro"],
        "utilities": ["electric", "water", "gas bill", "internet", "phone",
                       "utility"],
        "entertainment": ["movie", "game", "concert", "ticket", "netflix",
                          "spotify", "hulu"],
        "health": ["pharmacy", "medicine", "doctor", "hospital", "dental",
                   "prescription"],
        "clothing": ["shirt", "pants", "dress", "shoes", "jacket", "coat"],
    }

    def __init__(self):
        self.receipts = {}  # receipt_id -> Receipt
        self.user_receipts = defaultdict(list)
        self.hash_index = {}  # content_hash -> receipt_id

    def scan_text(self, user_id: str, text: str) -> dict:
        """Parse receipt text and create receipt."""
        parsed = self._parse_text(text)

        receipt_id = str(uuid4())[:8]
        receipt = Receipt(
            receipt_id=receipt_id,
            store=parsed["store"],
            total=parsed["total"],
            date=parsed["date"],
            items=parsed["items"],
            raw_text=text,
            category=parsed["category"],
            tax=parsed["tax"],
            tip=parsed["tip"],
        )

        # Duplicate check
        content_hash = receipt.content_hash
        if content_hash in self.hash_index:
            return {
                "status": "duplicate",
                "existing_receipt_id": self.hash_index[content_hash],
                "message": "This receipt appears to be a duplicate",
            }

        self.receipts[receipt_id] = receipt
        self.user_receipts[user_id].append(receipt_id)
        self.hash_index[content_hash] = receipt_id

        return {
            "status": "scanned",
            **receipt.to_dict(),
        }

    def upload_receipt(self, user_id: str, store: str, total: float,
                        date: str, items: list = None, raw_text: str = "",
                        category: str = "", tax: float = 0,
                        tip: float = 0,
                        payment_method: str = "") -> dict:
        """Manually upload receipt data."""
        receipt_id = str(uuid4())[:8]
        parsed_items = []
        if items:
            for item in items:
                if isinstance(item, dict):
                    parsed_items.append(ReceiptItem(
                        name=item.get("name", ""),
                        quantity=float(item.get("quantity", 1)),
                        unit_price=float(item.get("unit_price", 0)),
                        total=float(item.get("total", 0)),
                        category=item.get("category", ""),
                    ))

        receipt = Receipt(
            receipt_id=receipt_id, store=store, total=total, date=date,
            items=parsed_items, raw_text=raw_text, category=category,
            tax=tax, tip=tip, payment_method=payment_method,
        )

        content_hash = receipt.content_hash
        if content_hash in self.hash_index:
            return {"status": "duplicate",
                    "existing_receipt_id": self.hash_index[content_hash]}

        self.receipts[receipt_id] = receipt
        self.user_receipts[user_id].append(receipt_id)
        self.hash_index[content_hash] = receipt_id
        return {"status": "uploaded", **receipt.to_dict()}

    def get_receipt(self, receipt_id: str) -> dict:
        """Get receipt by ID."""
        if receipt_id not in self.receipts:
            return {"error": "Receipt not found"}
        return self.receipts[receipt_id].to_dict()

    def search(self, user_id: str, query: str = None,
                store: str = None, category: str = None,
                date_from: str = None, date_to: str = None,
                min_amount: float = None, max_amount: float = None) -> list[dict]:
        """Search receipts with filters."""
        receipt_ids = self.user_receipts.get(user_id, [])
        results = []

        for rid in receipt_ids:
            receipt = self.receipts.get(rid)
            if not receipt:
                continue

            if store and store.lower() not in receipt.store.lower():
                continue
            if category and category.lower() != receipt.category.lower():
                continue
            if date_from and receipt.date < date_from:
                continue
            if date_to and receipt.date > date_to:
                continue
            if min_amount and receipt.total < min_amount:
                continue
            if max_amount and receipt.total > max_amount:
                continue
            if query:
                query_lower = query.lower()
                match = (query_lower in receipt.store.lower() or
                        any(query_lower in i.name.lower() for i in receipt.items))
                if not match:
                    continue

            results.append(receipt.to_dict())

        return sorted(results, key=lambda x: x["date"], reverse=True)

    def get_summary(self, user_id: str) -> dict:
        """Get receipt statistics."""
        receipt_ids = self.user_receipts.get(user_id, [])
        receipts = [self.receipts[rid] for rid in receipt_ids
                   if rid in self.receipts]

        total_spent = sum(r.total for r in receipts)
        by_category = defaultdict(float)
        by_store = defaultdict(float)

        for r in receipts:
            by_category[r.category] += r.total
            by_store[r.store] += r.total

        return {
            "total_receipts": len(receipts),
            "total_spent": round(total_spent, 2),
            "avg_receipt": round(total_spent / max(len(receipts), 1), 2),
            "by_category": {k: round(v, 2) for k, v in
                           sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:10]},
            "top_stores": {k: round(v, 2) for k, v in
                          sorted(by_store.items(), key=lambda x: x[1], reverse=True)[:10]},
        }

    def export_data(self, user_id: str, format: str = "json") -> dict:
        """Export receipt data."""
        receipt_ids = self.user_receipts.get(user_id, [])
        receipts = [self.receipts[rid].to_dict() for rid in receipt_ids
                   if rid in self.receipts]

        if format == "csv":
            lines = ["receipt_id,store,total,date,category,tax,tip"]
            for r in receipts:
                lines.append(
                    f"{r['receipt_id']},{r['store']},{r['total']},"
                    f"{r['date']},{r['category']},{r['tax']},{r['tip']}"
                )
            return {"format": "csv", "data": "\n".join(lines)}
        return {"format": "json", "data": receipts}

    def delete(self, receipt_id: str) -> dict:
        """Delete a receipt."""
        if receipt_id not in self.receipts:
            return {"error": "Not found"}
        receipt = self.receipts.pop(receipt_id)
        if receipt.content_hash in self.hash_index:
            del self.hash_index[receipt.content_hash]
        return {"status": "deleted", "receipt_id": receipt_id}

    def _parse_text(self, text: str) -> dict:
        """Parse raw receipt text (simulated OCR)."""
        result = {
            "store": "Unknown",
            "total": 0.0,
            "date": datetime.utcnow().isoformat()[:10],
            "items": [],
            "category": "other",
            "tax": 0.0,
            "tip": 0.0,
        }

        lines = text.strip().split("\n")

        # Try to identify store from first lines
        for line in lines[:3]:
            for pattern, name in self.STORE_PATTERNS:
                if re.search(pattern, line.lower()):
                    result["store"] = name
                    break

        # Extract total
        total_match = re.search(r"total[:\s]*\$?(\d+\.?\d*)", text.lower())
        if total_match:
            result["total"] = float(total_match.group(1))

        # Extract date
        date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", text)
        if date_match:
            result["date"] = date_match.group(1).replace("/", "-")

        # Extract tax
        tax_match = re.search(r"tax[:\s]*\$?(\d+\.?\d*)", text.lower())
        if tax_match:
            result["tax"] = float(tax_match.group(1))

        # Extract tip
        tip_match = re.search(r"tip[:\s]*\$?(\d+\.?\d*)", text.lower())
        if tip_match:
            result["tip"] = float(tip_match.group(1))

        # Auto-categorize
        text_lower = text.lower()
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                result["category"] = cat
                break

        return result

    def get_all(self, user_id: str) -> list[dict]:
        """Get all receipts."""
        receipt_ids = self.user_receipts.get(user_id, [])
        return [self.receipts[rid].to_dict() for rid in receipt_ids
                if rid in self.receipts]
