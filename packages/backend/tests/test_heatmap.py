"""
Tests for the calendar heatmap endpoint.
"""

import json
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from app.models import Expense, Category


@pytest.fixture(autouse=True)
def seed_expenses(db_session):
    """Add some test expenses."""
    cat = Category(user_id=1, name="Food")
    db_session.add(cat)
    db_session.commit()

    today = date.today()
    for i in range(5):
        e = Expense(
            user_id=1,
            category_id=cat.id,
            amount=100 + i * 50,
            currency="INR",
            expense_type="EXPENSE",
            spent_at=today - timedelta(days=i),
        )
        db_session.add(e)
    db_session.commit()


class TestHeatmapEndpoint:
    def test_full_year(self, client, auth_header):
        r = client.get(f"/heatmap?year={date.today().year}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "days" in data
        assert data["year"] == date.today().year
        assert data["total_spending"] > 0
        assert data["active_days"] >= 1
        assert len(data["days"]) > 0

    def test_single_month(self, client, auth_header):
        r = client.get(f"/heatmap?year={date.today().year}&month={date.today().month}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["month"] == date.today().month
        assert all(d["intensity"] >= 0 and d["intensity"] <= 4 for d in data["days"])

    def test_missing_year(self, client, auth_header):
        r = client.get("/heatmap", headers=auth_header)
        assert r.status_code == 400

    def test_invalid_month(self, client, auth_header):
        r = client.get(f"/heatmap?year={date.today().year}&month=13", headers=auth_header)
        assert r.status_code == 400

    def test_intensity_scale(self, client, auth_header):
        r = client.get(f"/heatmap?year={date.today().year}&month={date.today().month}", headers=auth_header)
        data = r.get_json()
        active = [d for d in data["days"] if d["amount"] > 0]
        if len(active) >= 2:
            intensities = [d["intensity"] for d in active]
            assert max(intensities) == 4  # Highest spending day

    def test_auth_required(self, client):
        r = client.get(f"/heatmap?year={date.today().year}")
        assert r.status_code in (401, 422)
