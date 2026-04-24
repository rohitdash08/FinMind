from sqlalchemy import inspect


EXPECTED_INDEXES = {
    "categories": {"idx_categories_user_name"},
    "expenses": {
        "idx_expenses_user_spent_at",
        "idx_expenses_user_type_spent",
        "idx_expenses_user_category_spent",
        "idx_expenses_user_recurring_spent",
    },
    "recurring_expenses": {"idx_recurring_expenses_user_active_start"},
    "bills": {"idx_bills_user_active_due"},
    "reminders": {
        "idx_reminders_user_sent_send_at",
        "idx_reminders_user_bill",
    },
    "audit_logs": {
        "idx_audit_logs_user_created",
        "idx_audit_logs_action_created",
    },
}


def test_financial_query_indexes_created(app_fixture):
    with app_fixture.app_context():
        inspector = inspect(app_fixture.extensions["sqlalchemy"].engine)

        for table_name, expected_names in EXPECTED_INDEXES.items():
            actual_names = {idx["name"] for idx in inspector.get_indexes(table_name)}
            assert expected_names <= actual_names


def test_dashboard_summary_uses_index_friendly_range_filters(client, auth_header):
    client.post(
        "/expenses",
        json={
            "amount": "100.00",
            "description": "Salary",
            "expense_type": "INCOME",
            "date": "2026-04-05",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": "25.00",
            "description": "Groceries",
            "expense_type": "EXPENSE",
            "date": "2026-04-20",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": "999.00",
            "description": "Out of range",
            "expense_type": "EXPENSE",
            "date": "2026-05-01",
        },
        headers=auth_header,
    )

    response = client.get("/dashboard/summary?month=2026-04", headers=auth_header)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["summary"]["monthly_income"] == 100.0
    assert payload["summary"]["monthly_expenses"] == 25.0
    assert payload["summary"]["net_flow"] == 75.0
