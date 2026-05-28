"""Merchant frequency heatmap for FinMind.

Analyzes spending patterns across merchants by day-of-week and hour-of-day.
Returns a 2D heatmap showing when/where user spends most.
"""

import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.merchant_heatmap")


def generate_merchant_heatmap(
    transactions: list[dict],
    group_by: str = "day_of_week",  # day_of_week or hour_of_day
    top_n: int = 10,
) -> dict:
    """Generate merchant spending frequency heatmap.

    Args:
        transactions: List of transaction dicts with amount, merchant, date
        group_by: Grouping dimension - day_of_week or hour_of_day
        top_n: Number of top merchants to include

    Returns:
        Heatmap data with merchants as rows, time slots as columns
    """
    if group_by == "hour_of_day":
        time_slots = [str(h) for h in range(24)]
        time_labels = [f"{h}:00" for h in range(24)]
    else:
        time_slots = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        time_labels = time_slots

    # Count spending per merchant
    merchant_totals = defaultdict(float)
    for tx in transactions:
        merchant = tx.get("merchant", "Unknown")
        if merchant:
            merchant_totals[merchant] += float(tx.get("amount", 0))

    # Get top N merchants
    top_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:top_n]
    merchant_names = [m[0] for m in top_merchants]

    # Build heatmap matrix
    heatmap = {m: {slot: {"count": 0, "total": 0.0} for slot in time_slots} for m in merchant_names}

    for tx in transactions:
        merchant = tx.get("merchant", "Unknown")
        if merchant not in heatmap:
            continue

        date_str = tx.get("date") or tx.get("created_at")
        if not date_str:
            continue

        try:
            if isinstance(date_str, str):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = date_str
        except (ValueError, TypeError):
            continue

        if group_by == "hour_of_day":
            slot = str(dt.hour)
        else:
            slot = dt.strftime("%A")

        if slot in heatmap[merchant]:
            heatmap[merchant][slot]["count"] += 1
            heatmap[merchant][slot]["total"] += float(tx.get("amount", 0))

    # Format output
    matrix = []
    for merchant in merchant_names:
        row = {"merchant": merchant, "total_spent": round(merchant_totals[merchant], 2)}
        for slot in time_slots:
            data = heatmap[merchant][slot]
            row[slot] = {
                "transaction_count": data["count"],
                "total_amount": round(data["total"], 2),
            }
        matrix.append(row)

    return {
        "group_by": group_by,
        "time_slots": time_labels,
        "merchants": merchant_names,
        "heatmap": matrix,
    }


def get_merchant_patterns(transactions: list[dict]) -> dict:
    """Detect spending patterns per merchant.

    Returns insights like:
    - Most active day/hour per merchant
    - Average transaction amount
    - Spending trend (increasing/decreasing)
    """
    merchant_data = defaultdict(lambda: {"amounts": [], "dates": [], "total": 0.0})

    for tx in transactions:
        merchant = tx.get("merchant", "Unknown")
        amount = float(tx.get("amount", 0))
        date_str = tx.get("date") or tx.get("created_at")

        merchant_data[merchant]["amounts"].append(amount)
        merchant_data[merchant]["total"] += amount

        if date_str:
            try:
                if isinstance(date_str, str):
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    dt = date_str
                merchant_data[merchant]["dates"].append(dt)
            except:
                pass

    patterns = []
    for merchant, data in merchant_data.items():
        if not data["amounts"]:
            continue

        avg_amount = data["total"] / len(data["amounts"])

        # Most active day
        day_counts = defaultdict(int)
        hour_counts = defaultdict(int)
        for dt in data["dates"]:
            day_counts[dt.strftime("%A")] += 1
            hour_counts[dt.hour] += 1

        most_active_day = max(day_counts, key=day_counts.get) if day_counts else None
        most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

        # Trend
        trend = "stable"
        if len(data["amounts"]) >= 3:
            first_half = sum(data["amounts"][:len(data["amounts"])//2]) / (len(data["amounts"])//2)
            second_half = sum(data["amounts"][len(data["amounts"])//2:]) / (len(data["amounts"]) - len(data["amounts"])//2)
            if second_half > first_half * 1.2:
                trend = "increasing"
            elif second_half < first_half * 0.8:
                trend = "decreasing"

        patterns.append({
            "merchant": merchant,
            "total_spent": round(data["total"], 2),
            "transaction_count": len(data["amounts"]),
            "average_amount": round(avg_amount, 2),
            "most_active_day": most_active_day,
            "most_active_hour": f"{most_active_hour}:00" if most_active_hour is not None else None,
            "trend": trend,
        })

    return {"patterns": sorted(patterns, key=lambda x: x["total_spent"], reverse=True)}
