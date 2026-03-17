"""Tests for the Dynamic Budget Suggestions feature (issue #73).

Covers:
- 3-6 month data analysis
- Confidence scoring
- Per-category suggestions with trends
- Cache behavior
- Edge cases (no data, single month, etc.)
- Gemini AI integration (mocked)
- OpenAI integration (mocked)
- AI fallback chain (Gemini -> OpenAI -> heuristic)
- JSON parsing from AI responses
- Financial analyst persona validation
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from dateutil.relativedelta import relativedelta


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    categories = r.get_json()
    return next(c["id"] for c in categories if c["name"] == name)


def _add_expense(
    client, auth_header, amount, desc, dt, category_id=None, expense_type="EXPENSE"
):
    payload = {
        "amount": amount,
        "description": desc,
        "date": dt if isinstance(dt, str) else dt.isoformat(),
        "expense_type": expense_type,
    }
    if category_id:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _seed_multi_month_expenses(client, auth_header, food_id, transport_id, months=6):
    """Seed expenses across multiple months for realistic testing."""
    today = date.today().replace(day=15)
    for i in range(1, months + 1):
        target = today - relativedelta(months=i)
        _add_expense(
            client, auth_header, 300 + (i * 10), f"Groceries month-{i}", target, food_id
        )
        _add_expense(
            client, auth_header, 150 + (i * 5), f"Gas month-{i}", target, transport_id
        )
        _add_expense(client, auth_header, 100, f"Misc month-{i}", target)


class TestBudgetSuggestionEndpoint:
    """Test the /insights/budget-suggestion endpoint."""

    def test_returns_suggestion_with_no_data(self, client, auth_header):
        """When user has no expenses, should return a default suggestion."""
        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert "month" in data
        assert "suggested_total" in data
        assert data["suggested_total"] == 500.0
        assert "breakdown" in data
        assert data["breakdown"]["needs"] == 250.0
        assert data["breakdown"]["wants"] == 150.0
        assert data["breakdown"]["savings"] == 100.0
        assert "confidence" in data
        assert data["confidence"]["score"] == 0.0
        assert data["confidence"]["label"] == "no_data"
        assert data["confidence"]["months_analyzed"] == 0
        assert data["method"] == "heuristic_default"
        assert isinstance(data["category_suggestions"], list)
        assert len(data["category_suggestions"]) == 0

    def test_returns_suggestion_with_single_month(self, client, auth_header):
        """With only 1 month of data, should have low confidence."""
        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 500, "Groceries", target, food_id)
        _add_expense(client, auth_header, 200, "Eating out", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert data["confidence"]["months_analyzed"] == 1
        assert data["confidence"]["score"] > 0
        assert data["confidence"]["score"] < 0.5
        assert data["suggested_total"] > 0
        assert len(data["category_suggestions"]) >= 1

    def test_returns_suggestion_with_multi_month_data(self, client, auth_header):
        """With 6 months of data, should have high confidence."""
        food_id = _create_category(client, auth_header, "Food")
        transport_id = _create_category(client, auth_header, "Transport")
        _seed_multi_month_expenses(client, auth_header, food_id, transport_id, months=6)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert data["confidence"]["months_analyzed"] >= 3
        assert data["confidence"]["score"] >= 0.6
        assert data["method"] == "heuristic"
        assert data["suggested_total"] > 0

        assert "spending_trend" in data
        assert data["spending_trend"]["direction"] in (
            "increasing",
            "decreasing",
            "stable",
        )
        assert isinstance(data["spending_trend"]["change_pct"], (int, float))

        cats = data["category_suggestions"]
        assert len(cats) >= 2
        for cat in cats:
            assert "category_name" in cat
            assert "suggested_limit" in cat
            assert "average_spending" in cat
            assert "trend_pct" in cat
            assert "trend_direction" in cat
            assert cat["trend_direction"] in ("increasing", "decreasing", "stable")
            assert "months_with_data" in cat
            assert "monthly_history" in cat

    def test_data_range_reflects_actual_months(self, client, auth_header):
        """data_range should accurately reflect the analyzed period."""
        food_id = _create_category(client, auth_header, "Food")
        _seed_multi_month_expenses(client, auth_header, food_id, food_id, months=4)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        dr = data["data_range"]
        assert dr["months_requested"] == 6
        assert dr["months_with_data"] >= 1
        assert "oldest_month" in dr
        assert "newest_month" in dr

    def test_monthly_totals_included(self, client, auth_header):
        """Response should include monthly_totals dict."""
        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=2)
        _add_expense(client, auth_header, 400, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        assert "monthly_totals" in data
        assert isinstance(data["monthly_totals"], dict)

    def test_lookback_param_3_months(self, client, auth_header):
        """When months=3, should only look back 3 months."""
        food_id = _create_category(client, auth_header, "Food")
        _seed_multi_month_expenses(client, auth_header, food_id, food_id, months=6)

        r = client.get("/insights/budget-suggestion?months=3", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["data_range"]["months_requested"] == 3

    def test_lookback_param_clamped(self, client, auth_header):
        """Lookback should be clamped between 3 and 6."""
        r = client.get("/insights/budget-suggestion?months=1", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["data_range"]["months_requested"] == 3

        r = client.get("/insights/budget-suggestion?months=12", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["data_range"]["months_requested"] == 6

    def test_month_param_accepted(self, client, auth_header):
        """Custom month parameter should be reflected in response."""
        r = client.get("/insights/budget-suggestion?month=2026-01", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["month"] == "2026-01"

    def test_invalid_month_rejected(self, client, auth_header):
        """Invalid month format should return 400."""
        r = client.get("/insights/budget-suggestion?month=invalid", headers=auth_header)
        assert r.status_code == 400
        assert "invalid month" in r.get_json()["error"]

    def test_income_excluded_from_suggestions(self, client, auth_header):
        """INCOME entries should not be counted as spending."""
        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 5000, "Salary", target, expense_type="INCOME")
        _add_expense(client, auth_header, 300, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        assert data["suggested_total"] < 1000
        for cat in data["category_suggestions"]:
            if cat["category_name"] == "Food":
                assert cat["average_spending"] <= 300


class TestConfidenceScoring:
    """Test the confidence score logic specifically."""

    def test_zero_months_gives_zero_confidence(self, client, auth_header):
        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()
        assert data["confidence"]["score"] == 0.0
        assert data["confidence"]["label"] == "no_data"

    def test_more_months_gives_higher_confidence(self, client, auth_header):
        """Confidence should increase as more months of data are available."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)

        scores = []
        for i in range(1, 6):
            target = today - relativedelta(months=i)
            _add_expense(client, auth_header, 200, f"Food-{i}", target, food_id)
            r = client.get("/insights/budget-suggestion", headers=auth_header)
            data = r.get_json()
            scores.append(data["confidence"]["score"])

        for j in range(1, len(scores)):
            assert (
                scores[j] >= scores[j - 1]
            ), f"Confidence should be non-decreasing: {scores}"


class TestCategoryTrends:
    """Test per-category trend analysis."""

    def test_increasing_trend_detected(self, client, auth_header):
        """When spending increases each month, trend should be 'increasing'."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)

        amounts = [100, 200, 300, 400, 500]
        for i, amount in enumerate(amounts):
            target = today - relativedelta(months=len(amounts) - i)
            _add_expense(client, auth_header, amount, f"Food-{i}", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        food_cat = next(
            (c for c in data["category_suggestions"] if c["category_name"] == "Food"),
            None,
        )
        assert food_cat is not None
        assert food_cat["trend_direction"] == "increasing"
        assert food_cat["trend_pct"] > 0

    def test_decreasing_trend_detected(self, client, auth_header):
        """When spending decreases each month, trend should be 'decreasing'."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)

        amounts = [500, 400, 300, 200, 100]
        for i, amount in enumerate(amounts):
            target = today - relativedelta(months=len(amounts) - i)
            _add_expense(client, auth_header, amount, f"Food-{i}", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        food_cat = next(
            (c for c in data["category_suggestions"] if c["category_name"] == "Food"),
            None,
        )
        assert food_cat is not None
        assert food_cat["trend_direction"] == "decreasing"
        assert food_cat["trend_pct"] < 0

    def test_stable_trend_detected(self, client, auth_header):
        """When spending is roughly constant, trend should be 'stable'."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)

        for i in range(1, 5):
            target = today - relativedelta(months=i)
            _add_expense(client, auth_header, 300, f"Food-{i}", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        food_cat = next(
            (c for c in data["category_suggestions"] if c["category_name"] == "Food"),
            None,
        )
        assert food_cat is not None
        assert food_cat["trend_direction"] == "stable"

    def test_monthly_history_per_category(self, client, auth_header):
        """Each category should include monthly_history dict."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)

        for i in range(1, 4):
            target = today - relativedelta(months=i)
            _add_expense(client, auth_header, 250, f"Food-{i}", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        food_cat = next(
            (c for c in data["category_suggestions"] if c["category_name"] == "Food"),
            None,
        )
        assert food_cat is not None
        assert isinstance(food_cat["monthly_history"], dict)
        assert len(food_cat["monthly_history"]) > 0


class TestBreakdownLogic:
    """Test the 50/30/20 breakdown logic."""

    def test_breakdown_sums_to_suggested_total(self, client, auth_header):
        """Needs + wants + savings should equal suggested_total."""
        food_id = _create_category(client, auth_header, "Food")
        today = date.today().replace(day=15)
        for i in range(1, 4):
            target = today - relativedelta(months=i)
            _add_expense(client, auth_header, 500, f"Food-{i}", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        bd = data["breakdown"]
        total = bd["needs"] + bd["wants"] + bd["savings"]
        assert abs(total - data["suggested_total"]) < 0.02

    def test_default_breakdown_ratios(self, client, auth_header):
        """Breakdown should follow 50/30/20 ratios."""
        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        total = data["suggested_total"]
        assert data["breakdown"]["needs"] == round(total * 0.5, 2)
        assert data["breakdown"]["wants"] == round(total * 0.3, 2)
        assert data["breakdown"]["savings"] == round(total * 0.2, 2)


# ---------------------------------------------------------------------------
# Mock AI response helpers
# ---------------------------------------------------------------------------

MOCK_GEMINI_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "suggested_total": 1200.0,
                                "breakdown": {
                                    "needs": 600.0,
                                    "wants": 360.0,
                                    "savings": 240.0,
                                },
                                "category_suggestions": [
                                    {
                                        "category_name": "Food",
                                        "suggested_limit": 400.0,
                                        "reason": "Spending trend is stable",
                                    }
                                ],
                                "insights": ["Food spending is consistent"],
                                "tips": [
                                    "Meal-prep to cut grocery spend 15%",
                                    "Set a weekly dining-out cap of 50",
                                ],
                            }
                        )
                    }
                ]
            }
        }
    ]
}


MOCK_OPENAI_RESPONSE_JSON = json.dumps(
    {
        "suggested_total": 1100.0,
        "breakdown": {"needs": 550.0, "wants": 330.0, "savings": 220.0},
        "category_suggestions": [
            {
                "category_name": "Food",
                "suggested_limit": 380.0,
                "reason": "Below average — keep it up",
            }
        ],
        "insights": ["Overall spending trending down 5% — great progress"],
        "tips": ["Automate savings on payday", "Review subscriptions quarterly"],
    }
)


class TestGeminiIntegration:
    """Test Gemini AI budget generation (mocked HTTP calls)."""

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_returns_ai_budget(
        self, mock_settings, mock_post, client, auth_header
    ):
        """When Gemini key is set and API succeeds, method should be 'gemini'."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_GEMINI_RESPONSE
        mock_post.return_value = mock_resp

        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 400, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert data["method"] == "gemini"
        assert data["suggested_total"] == 1200.0
        assert data["breakdown"]["needs"] == 600.0
        assert "insights" in data
        assert len(data["insights"]) >= 1
        assert "tips" in data
        assert len(data["tips"]) >= 1
        assert "confidence" in data
        assert "month" in data

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_sends_persona_in_prompt(
        self, mock_settings, mock_post, client, auth_header
    ):
        """The Gemini prompt should include the financial analyst persona."""
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_GEMINI_RESPONSE
        mock_post.return_value = mock_resp

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200

        call_args = mock_post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json", {})
        prompt_text = body["contents"][0]["parts"][0]["text"]
        assert "financial analyst" in prompt_text.lower()
        assert "50/30/20" in prompt_text
        assert FINANCIAL_ANALYST_PERSONA[:40] in prompt_text

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_includes_spending_data_in_prompt(
        self, mock_settings, mock_post, client, auth_header
    ):
        """Prompt should include monthly totals and category breakdown."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_GEMINI_RESPONSE
        mock_post.return_value = mock_resp

        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 500, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200

        call_args = mock_post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json", {})
        prompt_text = body["contents"][0]["parts"][0]["text"]
        assert "Monthly totals" in prompt_text
        assert "Category breakdown" in prompt_text

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_failure_falls_back_to_heuristic(
        self, mock_settings, mock_post, client, auth_header
    ):
        """When Gemini API fails, should fallback to heuristic."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_post.side_effect = Exception("429 Too Many Requests")

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] in ("heuristic", "heuristic_default")

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_response_with_markdown_fences(
        self, mock_settings, mock_post, client, auth_header
    ):
        """Gemini sometimes wraps JSON in markdown fences — parser handles it."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        fenced_json = (
            "```json\n"
            + json.dumps(
                {
                    "suggested_total": 900.0,
                    "breakdown": {
                        "needs": 450.0,
                        "wants": 270.0,
                        "savings": 180.0,
                    },
                    "category_suggestions": [],
                    "insights": ["Good savings habit"],
                    "tips": ["Track daily expenses"],
                }
            )
            + "\n```"
        )

        fenced_response = {
            "candidates": [{"content": {"parts": [{"text": fenced_json}]}}]
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = fenced_response
        mock_post.return_value = mock_resp

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] == "gemini"
        assert data["suggested_total"] == 900.0

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_data_range_populated(
        self, mock_settings, mock_post, client, auth_header
    ):
        """Gemini response should include data_range and monthly_totals."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_GEMINI_RESPONSE
        mock_post.return_value = mock_resp

        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 300, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        data = r.get_json()

        assert "data_range" in data
        assert data["data_range"]["months_requested"] == 6
        assert data["data_range"]["months_with_data"] >= 1
        assert "monthly_totals" in data


class TestOpenAIIntegration:
    """Test OpenAI budget generation (mocked client)."""

    @patch("app.services.ai.OpenAI")
    @patch("app.services.ai._settings")
    def test_openai_returns_ai_budget(
        self, mock_settings, mock_openai_cls, client, auth_header
    ):
        """When OpenAI key is set and API succeeds, method should be 'openai'."""
        mock_settings.gemini_api_key = None
        mock_settings.openai_api_key = "fake-openai-key"

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = MOCK_OPENAI_RESPONSE_JSON
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        food_id = _create_category(client, auth_header, "Food")
        target = date.today().replace(day=15) - relativedelta(months=1)
        _add_expense(client, auth_header, 350, "Groceries", target, food_id)

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()

        assert data["method"] == "openai"
        assert data["suggested_total"] == 1100.0
        assert "insights" in data
        assert "tips" in data
        assert data["breakdown"]["needs"] == 550.0

    @patch("app.services.ai.OpenAI")
    @patch("app.services.ai._settings")
    def test_openai_uses_persona_as_system_message(
        self, mock_settings, mock_openai_cls, client, auth_header
    ):
        """OpenAI call should send persona as system message."""
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        mock_settings.gemini_api_key = None
        mock_settings.openai_api_key = "fake-openai-key"

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = MOCK_OPENAI_RESPONSE_JSON
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == FINANCIAL_ANALYST_PERSONA
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    @patch("app.services.ai.OpenAI")
    @patch("app.services.ai._settings")
    def test_openai_failure_falls_back_to_heuristic(
        self, mock_settings, mock_openai_cls, client, auth_header
    ):
        """When OpenAI API fails, should fallback to heuristic."""
        mock_settings.gemini_api_key = None
        mock_settings.openai_api_key = "fake-openai-key"

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API rate limited")

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] in ("heuristic", "heuristic_default")


class TestAIFallbackChain:
    """Test the priority chain: Gemini -> OpenAI -> Heuristic."""

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_preferred_over_openai(
        self, mock_settings, mock_post, client, auth_header
    ):
        """When both keys are set, Gemini should be tried first."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = "fake-openai-key"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_GEMINI_RESPONSE
        mock_post.return_value = mock_resp

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] == "gemini"

    @patch("app.services.ai.OpenAI")
    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_gemini_fail_then_openai_used(
        self, mock_settings, mock_post, mock_openai_cls, client, auth_header
    ):
        """When Gemini fails, should fall through to OpenAI."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = "fake-openai-key"

        mock_post.side_effect = Exception("Gemini unavailable")

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = MOCK_OPENAI_RESPONSE_JSON
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] == "openai"

    @patch("app.services.ai.requests.post")
    @patch("app.services.ai._settings")
    def test_all_ai_fail_uses_heuristic(
        self, mock_settings, mock_post, client, auth_header
    ):
        """When all AI providers fail, heuristic should be used."""
        mock_settings.gemini_api_key = "fake-gemini-key"
        mock_settings.gemini_model = "gemini-1.5-flash"
        mock_settings.openai_api_key = None

        mock_post.side_effect = Exception("Network error")

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] in ("heuristic", "heuristic_default")

    @patch("app.services.ai._settings")
    def test_no_keys_uses_heuristic(self, mock_settings, client, auth_header):
        """When no AI keys are configured, heuristic is used directly."""
        mock_settings.gemini_api_key = None
        mock_settings.openai_api_key = None

        r = client.get("/insights/budget-suggestion", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["method"] in ("heuristic", "heuristic_default")


class TestParseAIJson:
    """Test the _parse_ai_json helper for various AI response formats."""

    def test_plain_json(self):
        from app.services.ai import _parse_ai_json

        result = _parse_ai_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_markdown_fences(self):
        from app.services.ai import _parse_ai_json

        text = '```json\n{"key": "value"}\n```'
        result = _parse_ai_json(text)
        assert result == {"key": "value"}

    def test_json_with_plain_fences(self):
        from app.services.ai import _parse_ai_json

        text = '```\n{"key": "value"}\n```'
        result = _parse_ai_json(text)
        assert result == {"key": "value"}

    def test_json_with_surrounding_whitespace(self):
        from app.services.ai import _parse_ai_json

        text = '  \n  {"key": "value"}  \n  '
        result = _parse_ai_json(text)
        assert result == {"key": "value"}

    def test_json_with_leading_text(self):
        from app.services.ai import _parse_ai_json

        text = 'Here is the JSON:\n{"suggested_total": 500}'
        result = _parse_ai_json(text)
        assert result["suggested_total"] == 500

    def test_invalid_json_raises(self):
        import pytest

        from app.services.ai import _parse_ai_json

        with pytest.raises(Exception):
            _parse_ai_json("not json at all")


class TestFinancialAnalystPersona:
    """Verify persona content meets requirements."""

    def test_persona_includes_key_elements(self):
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        assert "financial analyst" in FINANCIAL_ANALYST_PERSONA.lower()
        assert "50/30/20" in FINANCIAL_ANALYST_PERSONA
        assert "JSON" in FINANCIAL_ANALYST_PERSONA
        assert "trend" in FINANCIAL_ANALYST_PERSONA

    def test_persona_handles_manual_input(self):
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        assert "manual" in FINANCIAL_ANALYST_PERSONA.lower()
        assert "user" in FINANCIAL_ANALYST_PERSONA.lower()

    def test_persona_has_rules_section(self):
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        assert "Rules" in FINANCIAL_ANALYST_PERSONA
        assert "saving opportunity" in FINANCIAL_ANALYST_PERSONA

    def test_persona_has_personality_section(self):
        from app.services.ai import FINANCIAL_ANALYST_PERSONA

        assert "Personality" in FINANCIAL_ANALYST_PERSONA
        assert "Encouraging" in FINANCIAL_ANALYST_PERSONA
