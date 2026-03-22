import pytest

from FinMind import FinMind
from FinMind.smart_digest import SmartDigest


@pytest.fixture(scope="module")
    df = fm.get_stock_data("AAPL", start="2023-01-01", end="2023-01-31")
    assert not df.empty
    assert "close" in df.columns


def test_smart_digest_weekly_summary(fm):
    sd = SmartDigest(fm)
    summary = sd.weekly_summary("AAPL", weeks=2)

    assert summary["ticker"] == "AAPL"
    assert "period" in summary
    assert "start" in summary["period"]
    assert "end" in summary["period"]
    assert isinstance(summary["weekly_returns"], list)
    assert len(summary["weekly_returns"]) == 2
    assert isinstance(summary["avg_weekly_return"], float)
    assert summary["trend"] in {"up", "down", "flat"}