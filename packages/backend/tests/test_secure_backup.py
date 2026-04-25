from app.extensions import db
from app.models import AuditLog
from app.services.secure_backup import BackupDecryptError, decrypt_backup


def test_encrypted_backup_export_contains_user_financial_data(
    app_fixture, client, auth_header
):
    category = client.post(
        "/categories", json={"name": "Groceries"}, headers=auth_header
    )
    assert category.status_code == 201
    category_id = category.get_json()["id"]

    expense = client.post(
        "/expenses",
        json={
            "amount": "42.50",
            "currency": "USD",
            "description": "farmers market",
            "category_id": category_id,
            "spent_at": "2026-04-24",
        },
        headers=auth_header,
    )
    assert expense.status_code == 201

    response = client.post(
        "/auth/me/backup/export",
        json={"passphrase": "correct horse battery staple"},
        headers=auth_header,
    )
    assert response.status_code == 200
    envelope = response.get_json()
    assert envelope["encrypted"] is True
    assert envelope["algorithm"] == "Fernet-AES128-CBC-HMAC-SHA256"
    assert envelope["kdf"] == "PBKDF2-HMAC-SHA256"
    assert envelope["record_counts"]["expenses"] == 1
    assert "farmers market" not in envelope["ciphertext"]

    decrypted = decrypt_backup(envelope, "correct horse battery staple")
    assert decrypted["schema_version"] == "finmind.secure-backup.v1"
    assert decrypted["user"]["email"] == "test@example.com"
    assert decrypted["records"]["categories"][0]["name"] == "Groceries"
    assert decrypted["records"]["expenses"][0]["notes"] == "farmers market"
    assert decrypted["records"]["expenses"][0]["amount"] == "42.50"

    with app_fixture.app_context():
        audit = (
            db.session.query(AuditLog)
            .filter_by(action="encrypted_backup_exported")
            .one()
        )
        assert audit.user_id == 1


def test_encrypted_backup_export_rejects_weak_passphrase(client, auth_header):
    response = client.post(
        "/auth/me/backup/export",
        json={"passphrase": "short"},
        headers=auth_header,
    )
    assert response.status_code == 400
    assert "passphrase" in response.get_json()["error"]


def test_backup_decrypt_rejects_wrong_passphrase(client, auth_header):
    response = client.post(
        "/auth/me/backup/export",
        json={"passphrase": "correct horse battery staple"},
        headers=auth_header,
    )
    assert response.status_code == 200

    try:
        decrypt_backup(response.get_json(), "wrong horse battery staple")
        assert False, "wrong passphrase should fail"
    except BackupDecryptError:
        pass
