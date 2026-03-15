"""Tests for the Intelligent Transaction Categorization Service."""


class TestCategorizeEndpoint:
    """Tests for POST /categorize"""

    def test_categorize_known_merchant(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Starbucks Coffee Store #1234"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Food & Dining"
        assert data["confidence"] >= 0.9

    def test_categorize_transport(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Uber Trip - Downtown Airport"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Transportation"
        assert data["confidence"] >= 0.5

    def test_categorize_shopping(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Amazon.com Purchase - Electronics"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Shopping"
        assert data["confidence"] >= 0.9

    def test_categorize_unknown_returns_uncategorized(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "xyzzy29487 random gibberish"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Uncategorized"
        assert data["confidence"] == 0.0

    def test_categorize_empty_description_400(self, client, auth_header):
        r = client.post("/categorize", json={"description": ""}, headers=auth_header)
        assert r.status_code == 400

    def test_categorize_missing_description_400(self, client, auth_header):
        r = client.post("/categorize", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_categorize_entertainment(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Netflix Monthly Subscription"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Entertainment"
        assert data["confidence"] >= 0.9

    def test_categorize_bills(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Electricity Bill - MSEDCL May 2025"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Bills & Utilities"

    def test_categorize_health(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Apollo Hospital Lab Tests"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["category"] == "Health"

    def test_categorize_returns_alternatives(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Amazon AWS Cloud Services"},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        # Should match either Shopping or Subscriptions, with alternatives
        assert data["category"] in ("Shopping", "Subscriptions")
        assert "alternatives" in data


class TestBatchCategorize:
    """Tests for POST /categorize/batch"""

    def test_batch_categorize(self, client, auth_header):
        r = client.post(
            "/categorize/batch",
            json={
                "transactions": [
                    {"description": "Starbucks Coffee"},
                    {"description": "Uber Ride Home"},
                    {"description": "Amazon Order"},
                    {"description": "Netflix Subscription"},
                ]
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] == 4
        assert len(data["results"]) == 4
        categories = [r["category"] for r in data["results"]]
        assert "Food & Dining" in categories
        assert "Transportation" in categories
        assert "Shopping" in categories
        assert "Entertainment" in categories

    def test_batch_empty_list_400(self, client, auth_header):
        r = client.post(
            "/categorize/batch",
            json={"transactions": []},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_batch_too_many_400(self, client, auth_header):
        r = client.post(
            "/categorize/batch",
            json={"transactions": [{"description": f"test {i}"} for i in range(101)]},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_batch_missing_transactions_400(self, client, auth_header):
        r = client.post("/categorize/batch", json={}, headers=auth_header)
        assert r.status_code == 400


class TestLearnEndpoint:
    """Tests for POST /categorize/learn"""

    def test_learn_from_correction(self, client, auth_header):
        r = client.post(
            "/categorize/learn",
            json={
                "description": "Local Pizza Palace Delivery",
                "category": "Food & Dining",
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert data["learned_count"] >= 1
        assert "pizza" in data["keywords"]

    def test_learn_improves_categorization(self, client, auth_header):
        # First categorize — should be unknown or low confidence
        r1 = client.post(
            "/categorize",
            json={"description": "Wompalicious Gym Membership"},
            headers=auth_header,
        )
        assert r1.status_code == 200

        # Learn the correction
        r2 = client.post(
            "/categorize/learn",
            json={
                "description": "Wompalicious Gym Membership",
                "category": "Health",
            },
            headers=auth_header,
        )
        assert r2.status_code == 200
        assert r2.get_json()["status"] == "ok"

        # Categorize again — should now match "health" or the learned keyword
        r3 = client.post(
            "/categorize",
            json={"description": "Wompalicious Gym Membership"},
            headers=auth_header,
        )
        assert r3.status_code == 200
        # The keyword "wompalicious" or "gym" or "membership" should trigger
        assert r3.get_json()["confidence"] >= 0.5

    def test_learn_missing_category_400(self, client, auth_header):
        r = client.post(
            "/categorize/learn",
            json={"description": "test transaction"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_learn_missing_description_400(self, client, auth_header):
        r = client.post(
            "/categorize/learn",
            json={"category": "Food"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_learn_empty_description_400(self, client, auth_header):
        r = client.post(
            "/categorize/learn",
            json={"description": "", "category": "Food"},
            headers=auth_header,
        )
        assert r.status_code == 400


class TestRulesEndpoint:
    """Tests for GET /categorize/rules and DELETE /categorize/rules/:id"""

    def test_list_rules_empty(self, client, auth_header):
        r = client.get("/categorize/rules", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_rules_after_learning(self, client, auth_header):
        # Learn a rule
        client.post(
            "/categorize/learn",
            json={"description": "Some Unique Transaction XYZ", "category": "Shopping"},
            headers=auth_header,
        )
        r = client.get("/categorize/rules", headers=auth_header)
        assert r.status_code == 200
        rules = r.get_json()
        assert len(rules) >= 1
        assert any(r["category"] == "Shopping" for r in rules)

    def test_delete_rule(self, client, auth_header):
        # Learn a rule
        client.post(
            "/categorize/learn",
            json={"description": "Delete Me Transaction ABC", "category": "Entertainment"},
            headers=auth_header,
        )
        # Get rules
        rules = client.get("/categorize/rules", headers=auth_header).get_json()
        rule_id = rules[0]["id"]
        # Delete
        r = client.delete(f"/categorize/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 200
        # Verify deleted
        rules2 = client.get("/categorize/rules", headers=auth_header).get_json()
        assert not any(r["id"] == rule_id for r in rules2)

    def test_delete_nonexistent_rule_404(self, client, auth_header):
        r = client.delete("/categorize/rules/99999", headers=auth_header)
        assert r.status_code == 404


class TestConfidenceScoring:
    """Tests for confidence scoring accuracy."""

    def test_high_confidence_exact_match(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Netflix"},
            headers=auth_header,
        )
        data = r.get_json()
        assert data["confidence"] >= 0.95

    def test_medium_confidence_partial_match(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "Trip to the market"},
            headers=auth_header,
        )
        data = r.get_json()
        # "market" matches Food & Dining at 0.70
        assert data["confidence"] <= 0.80

    def test_low_confidence_no_match(self, client, auth_header):
        r = client.post(
            "/categorize",
            json={"description": "zzzznonexistent123"},
            headers=auth_header,
        )
        data = r.get_json()
        assert data["category"] == "Uncategorized"
