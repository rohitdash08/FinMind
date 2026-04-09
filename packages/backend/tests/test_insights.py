import pytest
from datetime import date
from unittest.mock import patch


# Fixtures client and auth_header are from conftest.py


@patch("app.services.ai.weekly_financial_summary")
def test_weekly_summary_endpoint(mock_weekly_financial_summary, client, auth_header):
    # Configure the mock to return a predictable response
    mock_weekly_financial_summary.return_value = {
        "year_week": "2023-W10",
        "total_expenses": 500.00,
        "total_income": 1500.00,
        "net_flow": 1000.00,
        "top_expenses_by_category": [
            {"category_id": "groceries", "amount": 200.00},
            {"category_id": "dining_out", "amount": 100.00},
        ],
        "spending_trend": {
            "last_week_expenses": 450.00,
            "change_pct": 11.11,
            "trend_description": "Spending slightly up.",
        },
        "insights": ["Good week!"],
        "recommendations": [],
        "persona": None,
        "method": "heuristic",
        "warnings": [],
    }

    # Test without specific week parameter (should use current week by default)
    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "year_week" in data
    assert data["total_expenses"] == 500.00
    assert data["net_flow"] == 1000.00
    mock_weekly_financial_summary.assert_called_once()
    # Check that uid is an integer (from get_jwt_identity) and week is default
    args, kwargs = mock_weekly_financial_summary.call_args
    assert isinstance(args[0], int)  # uid
    assert args[1].startswith(str(date.today().year))  # year_week, default to current

    mock_weekly_financial_summary.reset_mock()

    # Test with specific week parameter
    test_year_week = "2024-W05"
    r = client.get(
        f"/insights/weekly-summary?week={test_year_week}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["year_week"] == test_year_week
    mock_weekly_financial_summary.assert_called_once_with(
        args[0],  # uid (same as before)
        test_year_week,
        gemini_api_key=None,
        persona=None,
    )

    mock_weekly_financial_summary.reset_mock()

    # Test with custom headers (gemini_api_key, persona)
    custom_headers = {
        **auth_header,
        "X-Gemini-Api-Key": "test-gemini-key",
        "X-Insight-Persona": "saver",
    }
    r = client.get(
        f"/insights/weekly-summary?week={test_year_week}", headers=custom_headers
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["persona"] == "saver"  # Mocked response should reflect this
    mock_weekly_financial_summary.assert_called_once_with(
        args[0],  # uid
        test_year_week,
        gemini_api_key="test-gemini-key",
        persona="saver",
    )

    mock_weekly_financial_summary.reset_mock()

    # Test unauthenticated access
    r = client.get("/insights/weekly-summary")
    assert r.status_code == 401
    mock_weekly_financial_summary.assert_not_called()

    mock_weekly_financial_summary.reset_mock()

    # Test with invalid week format (should fallback to default)
    invalid_week_fmt = "2023_W10" # Invalid format
    r = client.get(
        f"/insights/weekly-summary?week={invalid_week_fmt}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    # It should use the default week if the provided one is invalid
    assert data["year_week"].startswith(str(date.today().year))
    mock_weekly_financial_summary.assert_called_once()
    assert mock_weekly_financial_summary.call_args.kwargs["year_week"].startswith(
        str(date.today().year)
    )

    mock_weekly_financial_summary.reset_mock()
    
    # Test with valid format but invalid week number (e.g., W00)
    invalid_week_num = "2023-W00"
    r = client.get(
        f"/insights/weekly-summary?week={invalid_week_num}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["year_week"].startswith(str(date.today().year))
    mock_weekly_financial_summary.assert_called_once()

    mock_weekly_financial_summary.reset_mock()

    # Test with valid format but invalid year (e.g., year 1000)
    invalid_year = "1000-W01"
    r = client.get(
        f"/insights/weekly-summary?week={invalid_year}", headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["year_week"].startswith(str(date.today().year))
    mock_weekly_financial_summary.assert_called_once()

