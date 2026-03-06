class TestAccounts:
    def test_create_account(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={
                "name": "Main Checking",
                "account_type": "checking",
                "institution": "HDFC Bank",
                "balance": 50000,
                "currency": "INR",
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Main Checking"
        assert data["account_type"] == "checking"
        assert data["institution"] == "HDFC Bank"
        assert data["balance"] == 50000
        assert data["currency"] == "INR"
        assert "id" in data

    def test_list_accounts(self, client, auth_header):
        client.post(
            "/accounts",
            json={"name": "Checking", "account_type": "checking", "balance": 1000},
            headers=auth_header,
        )
        client.post(
            "/accounts",
            json={"name": "Savings", "account_type": "savings", "balance": 5000},
            headers=auth_header,
        )
        r = client.get("/accounts", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2

    def test_get_account_detail(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "Credit Card", "account_type": "credit", "balance": -2000},
            headers=auth_header,
        )
        account_id = r.get_json()["id"]
        r = client.get(f"/accounts/{account_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Credit Card"
        assert r.get_json()["balance"] == -2000

    def test_update_account(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "Old Name", "account_type": "checking", "balance": 100},
            headers=auth_header,
        )
        account_id = r.get_json()["id"]
        r = client.put(
            f"/accounts/{account_id}",
            json={"name": "New Name", "balance": 9999},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "New Name"
        assert data["balance"] == 9999

    def test_delete_account(self, client, auth_header):
        r = client.post(
            "/accounts",
            json={"name": "To Delete", "account_type": "savings", "balance": 500},
            headers=auth_header,
        )
        account_id = r.get_json()["id"]
        r = client.delete(f"/accounts/{account_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "deleted"
        r = client.get("/accounts", headers=auth_header)
        ids = [a["id"] for a in r.get_json()]
        assert account_id not in ids
        r = client.get(f"/accounts/{account_id}", headers=auth_header)
        assert r.status_code == 404

    def test_overview_aggregation(self, client, auth_header):
        client.post("/accounts", json={"name": "Checking", "account_type": "checking", "balance": 10000, "currency": "INR"}, headers=auth_header)
        client.post("/accounts", json={"name": "Savings", "account_type": "savings", "balance": 25000, "currency": "INR"}, headers=auth_header)
        client.post("/accounts", json={"name": "USD Account", "account_type": "checking", "balance": 500, "currency": "USD"}, headers=auth_header)
        client.post("/accounts", json={"name": "Investment", "account_type": "investment", "balance": 100000, "currency": "INR"}, headers=auth_header)
        r = client.get("/accounts/overview", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_balance"] == 135500
        assert data["account_count"] == 4
        assert data["by_type"]["checking"] == 10500
        assert data["by_type"]["savings"] == 25000
        assert data["by_type"]["investment"] == 100000
        assert data["by_currency"]["INR"] == 135000
        assert data["by_currency"]["USD"] == 500

    def test_invalid_account_type(self, client, auth_header):
        r = client.post("/accounts", json={"name": "Bad", "account_type": "crypto"}, headers=auth_header)
        assert r.status_code == 400
        assert "invalid account_type" in r.get_json()["error"]

    def test_requires_auth(self, client):
        r = client.post("/accounts", json={"name": "Test", "account_type": "checking"})
        assert r.status_code == 401
        r = client.get("/accounts")
        assert r.status_code == 401
        r = client.get("/accounts/overview")
        assert r.status_code == 401
