"""Tests for response compression & payload optimization (issue #129)."""
import pytest
from unittest.mock import patch, MagicMock


def test_filter_fields_dict():
    from app.middleware.compression import filter_fields
    data = {"id": 1, "name": "Billy", "secret": "hidden"}
    result = filter_fields(data, "id,name")
    assert result == {"id": 1, "name": "Billy"}
    assert "secret" not in result


def test_filter_fields_list():
    from app.middleware.compression import filter_fields
    data = [{"id": 1, "x": "drop"}, {"id": 2, "x": "drop"}]
    result = filter_fields(data, "id")
    assert result == [{"id": 1}, {"id": 2}]


def test_filter_fields_empty_returns_original():
    from app.middleware.compression import filter_fields
    data = {"id": 1, "name": "test"}
    assert filter_fields(data, "") == data


def test_strip_nulls():
    from app.middleware.compression import strip_nulls
    data = {"id": 1, "note": None, "amount": 0, "name": "test"}
    result = strip_nulls(data)
    assert "note" not in result
    assert result["amount"] == 0  # 0 is not None, keep it
    assert result["id"] == 1


def test_strip_nulls_nested():
    from app.middleware.compression import strip_nulls
    data = {"user": {"email": "a@b.com", "phone": None}}
    result = strip_nulls(data)
    assert "phone" not in result["user"]
    assert result["user"]["email"] == "a@b.com"


def test_paginate_limits_results():
    from app.middleware.compression import paginate
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_request_context("/?limit=2&offset=0"):
        from app.extensions import db
        from app.models import Category
        with app.app_context():
            db.create_all()
            for i in range(5):
                db.session.add(Category(user_id=1, name=f"Cat{i}"))
            db.session.commit()
            q = db.session.query(Category).filter_by(user_id=1)
            items, meta = paginate(q, default_limit=10)
            assert len(items) == 2
            assert meta["total"] == 5
            assert meta["has_more"] is True
