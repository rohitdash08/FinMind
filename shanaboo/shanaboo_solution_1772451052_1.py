"""
Smart Digest – Weekly Financial Summary Generator

Generates concise, insight-rich weekly summaries from raw financial data.
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

import pandas as pd


class SmartDigest:
    """
    High-level helper that produces weekly summaries with trend analysis.

    Usage
    -----
    >>> fm = FinMind()
    >>> sd = SmartDigest(fm)
    >>> summary = sd.weekly_summary("AAPL", weeks=4)
    >>> print(summary)
    """

    def __init__(self, finmind_client) -> None:
        """
        Parameters
        ----------
        finmind_client : FinMind
            An authenticated FinMind client instance.
        """
        self.fm = finmind_client

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def weekly_summary(
        self,
        ticker: str,
        weeks: int = 4,
        *,
        end_date: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Return a structured weekly summary for the requested ticker.

        Parameters
       ----------
        ticker : str
            Stock symbol, e.g. "AAPL".
        weeks : int, default 4
            Number of weeks (ending on the most recent Friday) to analyse.
        end_date : str, optional
            ISO date string (YYYY-MM-DD) that defines the *inclusive* end of
            the last week.  Defaults to the most recent Friday.

        Returns
        -------
        dict
            {
                "ticker": str,
                "period": {"start": str, "end": str},
                "weekly_returns": List[float],
                "avg_weekly_return": float,
                "volatility": float,
                "trend": "up" | "down" | "flat",
                "insights": List[str],
            }
        """
        if end_date is None:
            # Most recent Friday
            today = dt.date.today()
            offset = (today.weekday() - 4) % 7
            end_date = (today - dt.timedelta(days=offset)).isoformat()

        df = self.fm.get_stock_data(ticker, start=None, end=end_date)
        if df.empty:
            raise ValueError(f"No data returned for {ticker}")

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

        # Resample to weekly (Friday close)
        weekly = df["close"].resample("W-FRI").last()
        weekly_returns = weekly.pct_change().dropna().tolist()

        if len(weekly_returns) < weeks:
            weeks = len(weekly_returns)

        recent_returns = weekly_returns[-weeks:]
        avg_return = float(pd.Series(recent_returns).mean())
        volatility = float(pd.Series(recent_returns).std())

        trend = "flat"
        if avg_return > 0.005:
            trend = "up"
        elif avg_return < -0.005:
            trend = "down"

        insights = []
        if abs(avg_return) > 0.02:
            insights.append("High average weekly movement")
        if volatility > 0.03:
            insights.append("Elevated volatility detected")

        return {
            "ticker": ticker,
            "period": {
                "start": weekly.index[-weeks].date().isoformat(),
                "end": weekly.index[-1].date().isoformat(),
            },
            "weekly_returns": recent_returns,
            "avg_weekly_return": avg_return,
            "volatility": volatility,
            "trend": trend,
            "insights": insights,
        }