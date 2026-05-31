def test_detect_insufficient_data(client, auth_header):
    r = client.get("/insights/lifestyle-inflation/detect?months=2", headers=auth_header)
    assert r.status_code == 200
    result = r.get_json()
    assert result["trend"] == "insufficient_data"


def test_detect_with_data(client, auth_header):
    for i in range(6):
        client.post(
            "/expenses",
            json={
                "amount": 100 + i * 10,
                "description": f"Expense {i}",
                "date": f"2026-{i+1:02d}-15",
            },
            headers=auth_header,
        )
    r = client.get("/insights/lifestyle-inflation/detect?months=6", headers=auth_header)
    assert r.status_code == 200
    result = r.get_json()
    assert "insights" in result
    assert "monthly_breakdown" in result
    assert len(result["monthly_breakdown"]) == 6
