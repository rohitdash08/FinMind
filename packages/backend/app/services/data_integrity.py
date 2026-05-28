"""Financial Data Integrity & Reconciliation Service.

Ensures financial data correctness:
- Checksum validation for transaction records
- Balance reconciliation (transactions vs. stated balances)
- Duplicate detection (amount + date + merchant matching)
- Orphan detection (references to non-existent records)
- Integrity audit reports
- Automatic repair suggestions
"""

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.integrity")


class IntegrityReport:
    """Result of a data integrity check."""

    def __init__(self, user_id: str):
        self.report_id = str(uuid4())
        self.user_id = user_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.checks_run = 0
        self.issues_found = 0
        self.issues = []
        self.passed = []

    def add_issue(self, check: str, severity: str, description: str,
                  record_id: str = "", suggestion: str = ""):
        self.issues_found += 1
        self.issues.append({
            "check": check,
            "severity": severity,  # critical, warning, info
            "description": description,
            "record_id": record_id,
            "suggestion": suggestion,
        })

    def add_passed(self, check: str, count: int = 0):
        self.passed.append({"check": check, "records_checked": count})

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "checks_run": self.checks_run,
            "issues_found": self.issues_found,
            "issues": self.issues,
            "passed": self.passed,
            "healthy": self.issues_found == 0,
        }


class DataIntegrityService:
    """Verify and maintain financial data integrity."""

    def __init__(self):
        pass

    def compute_checksum(self, record: dict) -> str:
        """Compute SHA-256 checksum of a financial record."""
        # Sort keys for deterministic hashing
        canonical = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def verify_checksum(self, record: dict, expected_checksum: str) -> bool:
        """Verify a record's integrity checksum."""
        actual = self.compute_checksum(record)
        return actual == expected_checksum

    def check_duplicates(self, transactions: list[dict]) -> list[dict]:
        """Detect duplicate transactions (same amount + date + merchant)."""
        seen = {}
        duplicates = []

        for tx in transactions:
            # Create a key from amount + date + merchant
            key = (
                round(float(tx.get("amount", 0)), 2),
                str(tx.get("date", ""))[:10],
                str(tx.get("merchant", tx.get("description", ""))).lower().strip(),
            )

            if key in seen:
                duplicates.append({
                    "type": "duplicate",
                    "severity": "warning",
                    "record_ids": [seen[key], tx.get("id", "")],
                    "description": f"Duplicate transaction: ${key[0]} on {key[1]} at {key[2]}",
                    "suggestion": "Review and delete the duplicate entry",
                })
            else:
                seen[key] = tx.get("id", "")

        return duplicates

    def check_balance_reconciliation(self, transactions: list[dict],
                                      stated_balance: float,
                                      starting_balance: float = 0) -> dict:
        """Reconcile transactions against stated balance."""
        calculated = starting_balance
        for tx in transactions:
            amount = float(tx.get("amount", 0))
            tx_type = tx.get("type", "expense")
            if tx_type == "income" or amount > 0:
                calculated += abs(amount)
            else:
                calculated -= abs(amount)

        discrepancy = round(abs(calculated - stated_balance), 2)

        return {
            "calculated_balance": round(calculated, 2),
            "stated_balance": round(stated_balance, 2),
            "discrepancy": discrepancy,
            "reconciled": discrepancy == 0,
            "transaction_count": len(transactions),
        }

    def check_orphan_references(self, transactions: list[dict],
                                 accounts: list[dict],
                                 categories: list[dict] = None) -> list[dict]:
        """Find transactions referencing non-existent accounts/categories."""
        orphans = []
        account_ids = {a.get("id") for a in accounts}
        category_ids = {c.get("id") for c in (categories or [])}

        for tx in transactions:
            tx_id = tx.get("id", "unknown")

            account_id = tx.get("account_id")
            if account_id and account_id not in account_ids:
                orphans.append({
                    "type": "orphan_account",
                    "severity": "critical",
                    "record_id": tx_id,
                    "description": f"Transaction references missing account: {account_id}",
                    "suggestion": "Reassign to valid account or create missing account",
                })

            category_id = tx.get("category_id")
            if category_id and category_ids and category_id not in category_ids:
                orphans.append({
                    "type": "orphan_category",
                    "severity": "warning",
                    "record_id": tx_id,
                    "description": f"Transaction references missing category: {category_id}",
                    "suggestion": "Reassign to valid category",
                })

        return orphans

    def check_data_completeness(self, transactions: list[dict]) -> list[dict]:
        """Check for missing required fields in transactions."""
        required_fields = ["id", "amount", "date", "type"]
        recommended_fields = ["merchant", "category", "account_id", "description"]
        issues = []

        for tx in transactions:
            tx_id = tx.get("id", "unknown")

            # Check required fields
            missing = [f for f in required_fields if not tx.get(f)]
            if missing:
                issues.append({
                    "type": "missing_required",
                    "severity": "critical",
                    "record_id": tx_id,
                    "description": f"Missing required fields: {', '.join(missing)}",
                    "suggestion": f"Populate {', '.join(missing)} for data integrity",
                })

            # Check recommended fields
            missing_rec = [f for f in recommended_fields if not tx.get(f)]
            if len(missing_rec) >= 3:
                issues.append({
                    "type": "incomplete_record",
                    "severity": "info",
                    "record_id": tx_id,
                    "description": f"Incomplete record missing: {', '.join(missing_rec)}",
                    "suggestion": "Fill in more details for better analytics",
                })

        return issues

    def run_full_audit(self, user_id: str, transactions: list[dict],
                       accounts: list[dict], categories: list[dict] = None,
                       stated_balance: float = 0,
                       starting_balance: float = 0) -> IntegrityReport:
        """Run comprehensive data integrity audit."""
        report = IntegrityReport(user_id)

        # 1. Duplicate check
        report.checks_run += 1
        dupes = self.check_duplicates(transactions)
        if dupes:
            for d in dupes:
                report.add_issue("duplicate", d["severity"], d["description"],
                               ",".join(d.get("record_ids", [])), d["suggestion"])
        else:
            report.add_passed("duplicate", len(transactions))

        # 2. Balance reconciliation
        report.checks_run += 1
        recon = self.check_balance_reconciliation(transactions, stated_balance, starting_balance)
        if not recon["reconciled"]:
            report.add_issue("reconciliation", "critical",
                           f"Balance discrepancy: ${recon['discrepancy']}",
                           suggestion=f"Expected ${recon['calculated_balance']}, stated ${recon['stated_balance']}")
        else:
            report.add_passed("reconciliation", 1)

        # 3. Orphan references
        report.checks_run += 1
        orphans = self.check_orphan_references(transactions, accounts, categories)
        if orphans:
            for o in orphans:
                report.add_issue("orphan", o["severity"], o["description"],
                               o["record_id"], o["suggestion"])
        else:
            report.add_passed("orphan", len(transactions))

        # 4. Data completeness
        report.checks_run += 1
        completeness = self.check_data_completeness(transactions)
        if completeness:
            for c in completeness:
                report.add_issue("completeness", c["severity"], c["description"],
                               c["record_id"], c["suggestion"])
        else:
            report.add_passed("completeness", len(transactions))

        logger.info(f"Integrity audit for {user_id}: {report.issues_found} issues found")
        return report
