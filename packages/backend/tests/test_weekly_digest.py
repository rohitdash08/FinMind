"""
每周财务摘要 API 测试
"""
from datetime import date, timedelta


def test_weekly_summary_returns_basic_fields(client, auth_header):
    """测试返回基础字段"""
    # 创建一些测试支出数据
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # 本周支出
    for i in range(3):
        r = client.post(
            "/expenses",
            json={
                "amount": 50 + i * 10,
                "description": f"Test spend {i}",
                "date": (monday + timedelta(days=i)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/weekly-digest/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # 检查必选字段
    assert "week_start" in payload
    assert "week_end" in payload
    assert "week_data" in payload
    assert "previous_week_data" in payload
    assert "comparison" in payload
    assert "highlights" in payload
    assert "insights" in payload
    assert "tips" in payload
    assert "method" in payload

    # 检查周数据
    week_data = payload["week_data"]
    assert "total_income" in week_data
    assert "total_expenses" in week_data
    assert "net_flow" in week_data
    assert "categories" in week_data
    assert "transaction_count" in week_data

    # 检查对比数据
    comparison = payload["comparison"]
    assert "total_income_pct_change" in comparison
    assert "total_expenses_pct_change" in comparison
    assert "net_flow_pct_change" in comparison


def test_weekly_summary_specific_week(client, auth_header):
    """测试获取指定周的数据"""
    specific_week = "2024-01-01"

    r = client.get(
        f"/weekly-digest/weekly-summary?week={specific_week}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week_start"] == "2024-01-01"
    assert payload["week_end"] == "2024-01-07"


def test_weekly_summary_heurisic_mode(client, auth_header):
    """没有 API key 时使用启发式模式"""
    r = client.get("/weekly-digest/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert len(payload["highlights"]) > 0
    assert len(payload["tips"]) > 0


def test_weekly_summary_calculates_net_flow(client, auth_header):
    """测试计算净现金流"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # 添加收入
    client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Income",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )

    # 添加支出
    client.post(
        "/expenses",
        json={
            "amount": 400,
            "description": "Expense",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get("/weekly-digest/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["week_data"]["total_income"] == 1000.0
    assert payload["week_data"]["total_expenses"] == 400.0
    assert payload["week_data"]["net_flow"] == 600.0


def test_weekly_summary_with_gemini_fallback(client, auth_header, monkeypatch):
    """测试 Gemini 失败后降级到启发式"""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(
        "app.services.weekly_digest._generate_gemini_summary", _boom
    )

    r = client.get(
        "/weekly-digest/weekly-summary",
        headers={**auth_header, "X-Gemini-Api-Key": "test-key"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    # 不应该有警告字段就成功（或者有警告也可以）


def test_send_email_endpoint_exists(client, auth_header):
    """邮件发送端点存在（即使未配置）"""
    r = client.post(
        "/weekly-digest/weekly-summary/send-email",
        json={},
        headers=auth_header,
    )
    # 即使未配置邮件服务，也应该返回 200
    assert r.status_code == 200
    payload = r.get_json()
    assert "sent" in payload
    # 未配置邮件时应该返回 False 和原因
    assert payload.get("sent") is False or payload.get("reason") is not None
