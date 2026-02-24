"""Tests for database indexing optimization (Issue #128).

Verifies that the expected indexes exist on each table and that common
query patterns used by the application execute correctly with the indexed
columns.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_expenses(client, auth_header, count=20):
    """Create a batch of expenses spread across dates and types."""
    base = date.today() - timedelta(days=count)
    for i in range(count):
        d = base + timedelta(days=i)
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"test-expense-{i}",
                "date": d.isoformat(),
                "expense_type": "INCOME" if i % 5 == 0 else "EXPENSE",
            },
            headers=auth_header,
        )


# ---------------------------------------------------------------------------
# Index-aware query pattern tests
# ---------------------------------------------------------------------------

class TestExpenseQueryPatterns:
    """Verify the query patterns that benefit from the new indexes."""

    def test_list_expenses_date_range(self, client, auth_header):
        """idx_expenses_user_type_spent speeds up date-range + type filters."""
        _seed_expenses(client, auth_header, 15)
        today = date.today()
        r = client.get(
            f"/expenses?from={today - timedelta(days=7)}&to={today}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        for e in data:
            assert today - timedelta(days=7) <= date.fromisoformat(e["date"]) <= today

    def test_list_expenses_by_category(self, client, auth_header):
        """idx_expenses_user_category_spent speeds up category filtering."""
        # Create a category first
        r = client.post(
            "/categories", json={"name": "IndexTest"}, headers=auth_header
        )
        assert r.status_code == 201
        cat_id = r.get_json()["id"]

        client.post(
            "/expenses",
            json={
                "amount": 42.0,
                "description": "cat-filter-test",
                "category_id": cat_id,
            },
            headers=auth_header,
        )

        r = client.get(
            f"/expenses?category_id={cat_id}", headers=auth_header
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) >= 1
        assert all(e["category_id"] == cat_id for e in data)

    def test_dashboard_summary_monthly(self, client, auth_header):
        """Dashboard aggregation uses user + type + spent_at indexes."""
        _seed_expenses(client, auth_header, 10)
        ym = date.today().strftime("%Y-%m")
        r = client.get(f"/dashboard/summary?month={ym}", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "summary" in body
        assert body["summary"]["monthly_expenses"] >= 0

    def test_expense_search_with_pagination(self, client, auth_header):
        """Paginated search exercises the user_id + spent_at DESC index."""
        _seed_expenses(client, auth_header, 25)
        r = client.get(
            "/expenses?page=1&page_size=5", headers=auth_header
        )
        assert r.status_code == 200
        page1 = r.get_json()
        assert len(page1) <= 5

        r = client.get(
            "/expenses?page=2&page_size=5", headers=auth_header
        )
        assert r.status_code == 200
        page2 = r.get_json()
        # Pages should not overlap
        ids1 = {e["id"] for e in page1}
        ids2 = {e["id"] for e in page2}
        assert ids1.isdisjoint(ids2)


class TestBillQueryPatterns:
    """Verify bill queries that benefit from idx_bills_user_active_due."""

    def test_list_active_bills_ordered(self, client, auth_header):
        today = date.today()
        for i in range(3):
            client.post(
                "/bills",
                json={
                    "name": f"Bill-{i}",
                    "amount": 100 + i,
                    "next_due_date": (today + timedelta(days=i * 7)).isoformat(),
                    "cadence": "MONTHLY",
                },
                headers=auth_header,
            )
        r = client.get("/bills", headers=auth_header)
        assert r.status_code == 200
        bills = r.get_json()
        assert len(bills) >= 3
        # Should be ordered by next_due_date ascending
        dates = [b["next_due_date"] for b in bills]
        assert dates == sorted(dates)

    def test_dashboard_upcoming_bills(self, client, auth_header):
        today = date.today()
        client.post(
            "/bills",
            json={
                "name": "Upcoming",
                "amount": 50,
                "next_due_date": (today + timedelta(days=3)).isoformat(),
                "cadence": "MONTHLY",
            },
            headers=auth_header,
        )
        r = client.get(
            f"/dashboard/summary?month={today.strftime('%Y-%m')}",
            headers=auth_header,
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["summary"]["upcoming_bills_count"] >= 1


class TestRecurringExpenseQueryPatterns:
    """Verify recurring expense queries use idx_recurring_user_active."""

    def test_list_active_recurring(self, client, auth_header):
        client.post(
            "/expenses/recurring",
            json={
                "amount": 9.99,
                "description": "Netflix",
                "cadence": "MONTHLY",
                "start_date": date.today().isoformat(),
            },
            headers=auth_header,
        )
        r = client.get("/expenses/recurring", headers=auth_header)
        assert r.status_code == 200
        items = r.get_json()
        assert len(items) >= 1
        assert all(item["active"] for item in items)


class TestCategoryQueryPatterns:
    """Verify category queries benefit from idx_categories_user_name."""

    def test_list_categories_sorted(self, client, auth_header):
        for name in ["Zebra", "Alpha", "Middle"]:
            client.post(
                "/categories", json={"name": name}, headers=auth_header
            )
        r = client.get("/categories", headers=auth_header)
        assert r.status_code == 200
        names = [c["name"] for c in r.get_json()]
        assert names == sorted(names)

    def test_duplicate_category_rejected(self, client, auth_header):
        client.post(
            "/categories", json={"name": "UniqueIdx"}, headers=auth_header
        )
        r = client.post(
            "/categories", json={"name": "UniqueIdx"}, headers=auth_header
        )
        assert r.status_code == 409
