from datetime import date, timedelta


def _monday(d: date = None) -> date:
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def _post_expense(client, headers, amount, days_ago=0, expense_type="EXPENSE"):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    r = client.post(
        "/expenses",
        json={"amount": amount, "description": "test", "date": d, "expense_type": expense_type},
        headers=headers,
    )
    assert r.status_code == 201
    return r


class TestWeeklyDigest:
    def test_returns_200_with_required_fields(self, client, auth_header):
        r = client.get("/insights/weekly-digest", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        for field in (
            "week_start", "week_end", "summary", "category_breakdown",
            "top_categories", "top_transactions", "upcoming_bills",
            "insights", "method",
        ):
            assert field in body, f"missing field: {field}"

    def test_summary_fields_present(self, client, auth_header):
        r = client.get("/insights/weekly-digest", headers=auth_header)
        summary = r.get_json()["summary"]
        for key in ("total_income", "total_expenses", "net_flow", "week_over_week_change_pct"):
            assert key in summary

    def test_expenses_reflected_in_digest(self, client, auth_header):
        _post_expense(client, auth_header, 200, days_ago=0)
        _post_expense(client, auth_header, 150, days_ago=1)
        r = client.get("/insights/weekly-digest", headers=auth_header)
        body = r.get_json()
        assert body["summary"]["total_expenses"] >= 350.0

    def test_income_reflected_in_digest(self, client, auth_header):
        _post_expense(client, auth_header, 1000, days_ago=0, expense_type="INCOME")
        _post_expense(client, auth_header, 300, days_ago=0)
        r = client.get("/insights/weekly-digest", headers=auth_header)
        body = r.get_json()
        assert body["summary"]["total_income"] >= 1000.0
        assert body["summary"]["net_flow"] >= 700.0

    def test_week_param_accepted(self, client, auth_header):
        monday = _monday().isoformat()
        r = client.get(f"/insights/weekly-digest?week={monday}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["week_start"] == monday

    def test_invalid_week_returns_400(self, client, auth_header):
        r = client.get("/insights/weekly-digest?week=not-a-date", headers=auth_header)
        assert r.status_code == 400

    def test_week_over_week_increase_detected(self, client, auth_header):
        monday = _monday()
        last_wed = (monday - timedelta(days=7)) + timedelta(days=2)
        this_wed = monday + timedelta(days=2)
        client.post(
            "/expenses",
            json={"amount": 50, "description": "t", "date": last_wed.isoformat(), "expense_type": "EXPENSE"},
            headers=auth_header,
        )
        client.post(
            "/expenses",
            json={"amount": 200, "description": "t", "date": this_wed.isoformat(), "expense_type": "EXPENSE"},
            headers=auth_header,
        )
        r = client.get(f"/insights/weekly-digest?week={monday.isoformat()}", headers=auth_header)
        assert r.get_json()["summary"]["week_over_week_change_pct"] > 0

    def test_insights_is_nonempty_list(self, client, auth_header):
        _post_expense(client, auth_header, 100)
        r = client.get("/insights/weekly-digest", headers=auth_header)
        insights = r.get_json()["insights"]
        assert isinstance(insights, list)
        assert len(insights) >= 1

    def test_gemini_key_triggers_gemini_path(self, client, auth_header, monkeypatch):
        captured = {}

        def _fake_gemini(uid, week_start, api_key, model, persona):
            captured["api_key"] = api_key
            return {
                "week_start": week_start,
                "week_end": week_start,
                "summary": {
                    "total_income": 0,
                    "total_expenses": 0,
                    "net_flow": 0,
                    "week_over_week_change_pct": 0,
                },
                "category_breakdown": [],
                "top_categories": [],
                "top_transactions": [],
                "upcoming_bills": [],
                "insights": ["AI insight"],
                "method": "gemini",
                "persona": persona,
            }

        monkeypatch.setattr("app.services.ai._gemini_weekly_digest", _fake_gemini)
        r = client.get(
            "/insights/weekly-digest",
            headers={**auth_header, "X-Gemini-Api-Key": "my-key"},
        )
        assert r.status_code == 200
        assert r.get_json()["method"] == "gemini"
        assert captured["api_key"] == "my-key"

    def test_gemini_failure_falls_back_to_heuristic(self, client, auth_header, monkeypatch):
        def _boom(*_a, **_k):
            raise RuntimeError("gemini down")

        monkeypatch.setattr("app.services.ai._gemini_weekly_digest", _boom)
        r = client.get(
            "/insights/weekly-digest",
            headers={**auth_header, "X-Gemini-Api-Key": "any"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["method"] == "heuristic"
        assert "gemini_unavailable" in body.get("warnings", [])

    def test_unauthenticated_returns_401(self, client):
        r = client.get("/insights/weekly-digest")
        assert r.status_code == 401
