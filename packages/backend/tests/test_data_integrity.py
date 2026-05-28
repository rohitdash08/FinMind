"""Tests for data integrity & reconciliation."""

import pytest


class TestChecksum:
    def test_compute(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        cs = svc.compute_checksum({"amount": 100, "date": "2024-01-01"})
        assert len(cs) == 16

    def test_verify_valid(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        record = {"amount": 100}
        cs = svc.compute_checksum(record)
        assert svc.verify_checksum(record, cs)

    def test_verify_invalid(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        assert not svc.verify_checksum({"amount": 100}, "wrongchecksum")


class TestDuplicates:
    def test_no_duplicates(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        txs = [
            {"id": "1", "amount": 50, "date": "2024-01-01", "merchant": "A"},
            {"id": "2", "amount": 60, "date": "2024-01-01", "merchant": "B"},
        ]
        assert svc.check_duplicates(txs) == []

    def test_find_duplicates(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        txs = [
            {"id": "1", "amount": 50, "date": "2024-01-01", "merchant": "A"},
            {"id": "2", "amount": 50, "date": "2024-01-01", "merchant": "A"},
        ]
        dupes = svc.check_duplicates(txs)
        assert len(dupes) == 1


class TestReconciliation:
    def test_balanced(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        txs = [{"amount": 100, "type": "income"}, {"amount": 30, "type": "expense"}]
        result = svc.check_balance_reconciliation(txs, stated_balance=70, starting_balance=0)
        assert result["reconciled"]

    def test_discrepancy(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        txs = [{"amount": 100, "type": "income"}]
        result = svc.check_balance_reconciliation(txs, stated_balance=50, starting_balance=0)
        assert not result["reconciled"]
        assert result["discrepancy"] == 50


class TestFullAudit:
    def test_healthy(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        report = svc.run_full_audit(
            user_id="u1",
            transactions=[{"id": "1", "amount": 100, "date": "2024-01-01", "type": "income"}],
            accounts=[{"id": "a1"}],
            stated_balance=100,
        )
        assert report.to_dict()["healthy"]

    def test_with_issues(self):
        from app.services.data_integrity import DataIntegrityService
        svc = DataIntegrityService()
        report = svc.run_full_audit(
            user_id="u1",
            transactions=[{"id": "1", "amount": 100, "date": "2024-01-01", "type": "income", "account_id": "missing"}],
            accounts=[],
            stated_balance=0,
        )
        assert report.issues_found > 0
