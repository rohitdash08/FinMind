"""Tests for PII Export & Delete (GDPR) service."""

import pytest


class TestPIIScanner:
    def test_scan_email(self):
        from app.services.gdpr_pii import PIIScanner
        scanner = PIIScanner()
        findings = scanner.scan_record({"email": "test@example.com"})
        assert any(f["pii_type"] == "email" for f in findings)

    def test_scan_name(self):
        from app.services.gdpr_pii import PIIScanner
        scanner = PIIScanner()
        findings = scanner.scan_record({"name": "John Doe"})
        assert any(f["pii_type"] == "personal_name" for f in findings)

    def test_scan_no_pii(self):
        from app.services.gdpr_pii import PIIScanner
        scanner = PIIScanner()
        findings = scanner.scan_record({"amount": 100, "category": "food"})
        assert len(findings) == 0


class TestDataExporter:
    def test_export_json(self):
        from app.services.gdpr_pii import DataExporter
        exporter = DataExporter()
        result = exporter.export_json({"transactions": [{"id": 1}]})
        assert "export_metadata" in result
        assert "Article 20" in result

    def test_export_csv(self):
        from app.services.gdpr_pii import DataExporter
        exporter = DataExporter()
        result = exporter.export_csv([{"id": 1, "name": "test"}], "test")
        assert "id,name" in result

    def test_full_package(self):
        from app.services.gdpr_pii import DataExporter
        exporter = DataExporter()
        package = exporter.generate_export_package({
            "transactions": [{"id": 1}],
            "settings": {"theme": "dark"},
        })
        assert "full_export.json" in package
        assert "transactions.csv" in package


class TestAnonymizer:
    def test_anonymize_email(self):
        from app.services.gdpr_pii import DataAnonymizer
        result = DataAnonymizer.anonymize_field("test@example.com", "email")
        assert "ANON_EMAIL" in result
        assert "test@example.com" not in result

    def test_anonymize_name(self):
        from app.services.gdpr_pii import DataAnonymizer
        result = DataAnonymizer.anonymize_field("John Doe", "personal_name")
        assert "ANON_NAME" in result

    def test_anonymize_record(self):
        from app.services.gdpr_pii import DataAnonymizer, PIIScanner
        scanner = PIIScanner()
        record = {"name": "John", "email": "john@test.com", "amount": 100}
        result = DataAnonymizer().anonymize_record(record, scanner)
        assert result["amount"] == 100  # Non-PII preserved
        assert "ANON" in result["name"]


class TestGDPRService:
    def test_export(self):
        from app.services.gdpr_pii import GDPRService
        svc = GDPRService()
        result = svc.process_export("user1", {
            "transactions": [{"id": "1", "amount": 100, "email": "test@test.com"}],
        })
        assert result["status"] == "completed"
        assert result["export_data"]["total_pii_fields"] > 0

    def test_deletion_anonymize(self):
        from app.services.gdpr_pii import GDPRService
        svc = GDPRService()
        result = svc.process_deletion("user1", {
            "transactions": [{"id": "1", "name": "John", "amount": 100}],
        }, anonymize_instead=True)
        assert result["status"] == "completed"
        assert result["deletion_log"][0]["action"] == "anonymized"

    def test_deletion_hard(self):
        from app.services.gdpr_pii import GDPRService
        svc = GDPRService()
        result = svc.process_deletion("user1", {
            "transactions": [{"id": "1", "name": "John"}],
        }, anonymize_instead=False)
        assert result["deletion_log"][0]["action"] == "deleted"

    def test_verify_deletion(self):
        from app.services.gdpr_pii import GDPRService
        svc = GDPRService()
        export_result = svc.process_export("user1", {"transactions": []})
        req_id = export_result["request_id"]

        verify = svc.verify_deletion(req_id, {"transactions": []})
        assert verify["verified"] is True

    def test_audit_log(self):
        from app.services.gdpr_pii import GDPRService
        svc = GDPRService()
        svc.process_export("user1", {"data": []})
        logs = svc.get_audit_log()
        assert len(logs) > 0
