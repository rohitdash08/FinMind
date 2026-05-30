from sqlalchemy import inspect


def test_database_indexes_exist_on_models(app_fixture):
    with app_fixture.app_context():
        from app.extensions import db
        from app import models

        inspector = inspect(db.engine)
        indexes = {}
        for table_name in ["expenses", "categories", "bills", "reminders"]:
            indexes[table_name] = {
                ix["name"]: ix["column_names"]
                for ix in inspector.get_indexes(table_name)
            }

        exp_idxs = indexes.get("expenses", {})
        assert any("user_id" in cols for name, cols in exp_idxs.items()), (
            "expenses missing user_id index"
        )

        cat_idxs = indexes.get("categories", {})
        assert any("user_id" in cols for name, cols in cat_idxs.items()), (
            "categories missing user_id index"
        )

        bill_idxs = indexes.get("bills", {})
        assert any(
            "user_id" in cols and "next_due_date" in cols
            for name, cols in bill_idxs.items()
        ), "bills missing user_id + next_due_date index"

        rem_idxs = indexes.get("reminders", {})
        assert any(
            "user_id" in cols and "created_at" in cols
            for name, cols in rem_idxs.items()
        ), "reminders missing user_id + created_at index"


def test_query_performance_logging_enabled(app_fixture):
    from app.observability import _query_log_enabled

    assert _query_log_enabled is True


def test_index_improves_category_query(app_fixture, client, auth_header):
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200


def test_index_improves_bill_query(app_fixture, client, auth_header):
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200


def test_index_improves_reminder_query(app_fixture, client, auth_header):
    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
