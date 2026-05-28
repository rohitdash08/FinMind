"""Tests for Bank Account Sync."""

import pytest


class TestBankSync:
    def test_register_account(self):
        from app.services.bank_sync import BankSyncService
        svc = BankSyncService()
        result = svc.register_account("acc1", "checking", "Chase", 1000)
        assert result["status"] == "registered"
        assert result["account"]["balance"] == 1000

    def test_sync_with_transactions(self):
        from app.services.bank_sync import BankSyncService
        svc = BankSyncService()
        svc.register_account("acc1", "checking", "Chase", 1000)
        txs = [
            {"amount": -50, "date": "2024-01-15", "description": "grocery"},
            {"amount": -30, "date": "2024-01-16", "description": "gas"},
        ]
        result = svc.sync_account("acc1", bank_transactions=txs)
        assert result["new_transactions"] == 2
        assert result["status"] == "completed"

    def test_deduplication(self):
        from app.services.bank_sync import BankSyncService
        svc = BankSyncService()
        svc.register_account("acc1", "checking", "Chase", 1000)
        txs = [{"amount": -50, "date": "2024-01-15", "description": "grocery"}]
        svc.sync_account("acc1", bank_transactions=txs)
        result = svc.sync_account("acc1", bank_transactions=txs)
        assert result["duplicates_skipped"] == 1

    def test_balance_reconciliation(self):
        from app.services.bank_sync import BankSyncService
        svc = BankSyncService()
        svc.register_account("acc1", "checking", "Chase", 1000)
        txs = [{"amount": -100, "date": "2024-01-15", "description": "rent"}]
        result = svc.sync_account("acc1", bank_transactions=txs, reported_balance=900)
        recon = result["account_results"]["balance_reconciliation"]
        assert recon["reconciled"] is True

    def test_sync_all(self):
        from app.services.bank_sync import BankSyncService
        svc = BankSyncService()
        svc.register_account("acc1", "checking", "Chase")
        svc.register_account("acc2", "savings", "Wells")
        result = svc.sync_all({"acc1": {"balance": 500}, "acc2": {"balance": 2000}})
        assert result["accounts_synced"] == 2
