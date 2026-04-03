from typing import Dict, List, Optional, Any
from collections import defaultdict
import uuid
import re
from datetime import datetime

# In-memory stores
_payee_aliases: Dict[str, Dict[str, Dict]] = defaultdict(dict)  # user_id -> {canonical: alias_info}

class PayeeAliasService:
    """
    Manages smart payee and merchant alias mappings.
    Normalizes messy merchant names (e.g., "AMZN*MKTP US" -> "Amazon") and
    allows users to create custom aliases.
    """

    NORMALIZATION_RULES = [
        ("amzn", "Amazon"),
        ("amazon", "Amazon"),
        ("netflix", "Netflix"),
        ("spotify", "Spotify"),
        ("apple.com/bill", "Apple"),
        ("apple itunes", "Apple"),
        ("google play", "Google"),
        ("google storage", "Google"),
        ("uber eats", "Uber Eats"),
        ("doordash", "DoorDash"),
        ("grubhub", "Grubhub"),
        ("airbnb", "Airbnb"),
        ("starbucks", "Starbucks"),
        ("mcdonald", "McDonald's"),
        ("whole foods", "Whole Foods"),
        ("costco", "Costco"),
        ("walmart", "Walmart"),
        ("chevron", "Chevron"),
        ("hulu", "Hulu"),
        ("disney", "Disney+"),
        ("paypal", "PayPal"),
        ("venmo", "Venmo"),
    ]

    def normalize(self, raw_name: str) -> str:
        cleaned = raw_name.strip().lower()
        cleaned = re.sub(r"^(tst\*|sq\*|pp\*|pos\*|pmt\*|debit\*)", "", cleaned)
        cleaned = re.sub(r"\s+(llc|inc|corp|co)\.?$", "", cleaned)
        cleaned = re.sub(r"\s+\d{4,}$", "", cleaned)
        cleaned = cleaned.strip()

        for pattern, canonical in self.NORMALIZATION_RULES:
            if pattern in cleaned:
                return canonical

        return raw_name.strip().title()

    def get_alias(self, user_id: str, raw_name: str) -> str:
        canonical = self.normalize(raw_name)
        user_aliases = _payee_aliases.get(user_id, {})
        if canonical in user_aliases:
            return user_aliases[canonical]["alias"]
        return canonical

    def set_alias(self, user_id: str, raw_name: str, alias: str) -> Dict:
        canonical = self.normalize(raw_name)
        record = {
            "id": str(uuid.uuid4()),
            "canonical": canonical,
            "alias": alias,
            "raw_name": raw_name,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        _payee_aliases[user_id][canonical] = record
        return record

    def delete_alias(self, user_id: str, canonical: str) -> bool:
        if canonical in _payee_aliases.get(user_id, {}):
            del _payee_aliases[user_id][canonical]
            return True
        return False

    def list_aliases(self, user_id: str) -> List[Dict]:
        return sorted(_payee_aliases.get(user_id, {}).values(), key=lambda x: x["alias"])

    def bulk_normalize(self, user_id: str, raw_names: List[str]) -> List[Dict]:
        results = []
        seen: Dict[str, str] = {}
        for raw in raw_names:
            if raw not in seen:
                seen[raw] = self.get_alias(user_id, raw)
            results.append({"raw": raw, "display": seen[raw]})
        return results

    def suggest_aliases(self, user_id: str, raw_names: List[str]) -> List[Dict]:
        suggestions = []
        seen = set()
        for raw in raw_names:
            if raw in seen:
                continue
            seen.add(raw)
            normalized = self.normalize(raw)
            if normalized != raw.strip().title() and normalized != raw.strip():
                suggestions.append({
                    "raw": raw,
                    "suggested": normalized,
                    "user_alias": _payee_aliases.get(user_id, {}).get(normalized, {}).get("alias"),
                })
        return suggestions