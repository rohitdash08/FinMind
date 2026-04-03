from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import statistics
import uuid

_transactions: Dict[str, List[Dict]] = defaultdict(list)

class AnomalyDetectionEngine:
    """
    Statistical anomaly detection for financial transactions.
    Uses Z-score, IQR, and pattern-based detection methods.
    """

    # Thresholds
    ZSCORE_THRESHOLD = 2.5
    IQR_MULTIPLIER = 2.0
    DUPLICATE_WINDOW_HOURS = 24

    def detect_anomalies(self, user_id: str, lookback_days: int = 90) -> List[Dict]:
        """Run all anomaly detectors and return combined results."""
        txns = self._get_recent_transactions(user_id, lookback_days)
        if len(txns) < 5:
            return []

        anomalies = []
        anomalies.extend(self._detect_amount_outliers(txns))
        anomalies.extend(self._detect_duplicate_transactions(txns))
        anomalies.extend(self._detect_velocity_spikes(txns))
        anomalies.extend(self._detect_category_anomalies(txns))

        # Deduplicate by transaction_id
        seen = set()
        deduped = []
        for a in anomalies:
            key = (a.get("transaction_id"), a.get("anomaly_type"))
            if key not in seen:
                seen.add(key)
                deduped.append(a)

        return sorted(deduped, key=lambda x: x.get("score", 0), reverse=True)

    def _detect_amount_outliers(self, txns: List[Dict]) -> List[Dict]:
        """Flag transactions with unusually high amounts (Z-score or IQR)."""
        amounts = [abs(float(t.get("amount", 0))) for t in txns]
        if len(amounts) < 3:
            return []

        mean_a = statistics.mean(amounts)
        std_a = statistics.stdev(amounts) if len(amounts) > 1 else 0
        q1 = sorted(amounts)[len(amounts) // 4]
        q3 = sorted(amounts)[3 * len(amounts) // 4]
        iqr = q3 - q1

        anomalies = []
        for txn in txns:
            amount = abs(float(txn.get("amount", 0)))
            z = (amount - mean_a) / std_a if std_a > 0 else 0
            iqr_flag = amount > q3 + self.IQR_MULTIPLIER * iqr

            if z > self.ZSCORE_THRESHOLD or iqr_flag:
                anomalies.append({
                    "id": str(uuid.uuid4()),
                    "transaction_id": txn.get("id"),
                    "anomaly_type": "amount_outlier",
                    "severity": "high" if z > 4 else "medium",
                    "score": round(min(z, 10), 2),
                    "description": f"Unusually high amount {amount:.2f} (z-score: {z:.1f}, mean: {mean_a:.2f})",
                    "amount": amount,
                    "date": txn.get("date"),
                    "category": txn.get("category"),
                })
        return anomalies

    def _detect_duplicate_transactions(self, txns: List[Dict]) -> List[Dict]:
        """Flag potential duplicate charges within a 24-hour window."""
        anomalies = []
        sorted_txns = sorted(txns, key=lambda t: t.get("date", ""))
        for i, t1 in enumerate(sorted_txns):
            for t2 in sorted_txns[i + 1:]:
                try:
                    d1 = datetime.fromisoformat(t1["date"])
                    d2 = datetime.fromisoformat(t2["date"])
                    if abs((d2 - d1).total_seconds()) > self.DUPLICATE_WINDOW_HOURS * 3600:
                        break
                    a1 = abs(float(t1.get("amount", 0)))
                    a2 = abs(float(t2.get("amount", 0)))
                    same_cat = t1.get("category") == t2.get("category")
                    same_amount = abs(a1 - a2) < 0.01
                    if same_amount and same_cat and a1 > 0:
                        anomalies.append({
                            "id": str(uuid.uuid4()),
                            "transaction_id": t2.get("id"),
                            "related_transaction_id": t1.get("id"),
                            "anomaly_type": "potential_duplicate",
                            "severity": "high",
                            "score": 8.0,
                            "description": f"Possible duplicate charge: {a2:.2f} in {t2.get('category')} within 24h",
                            "amount": a2,
                            "date": t2.get("date"),
                            "category": t2.get("category"),
                        })
                except (ValueError, KeyError):
                    continue
        return anomalies

    def _detect_velocity_spikes(self, txns: List[Dict]) -> List[Dict]:
        """Flag days with unusually high transaction frequency."""
        day_counts: Dict[str, int] = defaultdict(int)
        day_txns: Dict[str, List] = defaultdict(list)
        for t in txns:
            try:
                day = t["date"][:10]
                day_counts[day] += 1
                day_txns[day].append(t)
            except (KeyError, IndexError):
                pass

        if len(day_counts) < 5:
            return []

        counts = list(day_counts.values())
        mean_c = statistics.mean(counts)
        std_c = statistics.stdev(counts) if len(counts) > 1 else 0

        anomalies = []
        for day, count in day_counts.items():
            z = (count - mean_c) / std_c if std_c > 0 else 0
            if z > self.ZSCORE_THRESHOLD:
                anomalies.append({
                    "id": str(uuid.uuid4()),
                    "transaction_id": None,
                    "anomaly_type": "velocity_spike",
                    "severity": "medium",
                    "score": round(min(z, 10), 2),
                    "description": f"Unusually high transaction frequency on {day}: {count} transactions (avg: {mean_c:.1f})",
                    "date": day,
                    "transaction_count": count,
                })
        return anomalies

    def _detect_category_anomalies(self, txns: List[Dict]) -> List[Dict]:
        """Flag categories with sudden spending spikes."""
        by_cat: Dict[str, List[Tuple[str, float]]] = defaultdict(list)  # cat -> [(month, amount)]
        for t in txns:
            try:
                d = datetime.fromisoformat(t["date"])
                month_key = f"{d.year}-{d.month:02d}"
                cat = t.get("category", "uncategorized")
                amount = abs(float(t.get("amount", 0)))
                by_cat[cat].append((month_key, amount))
            except (ValueError, KeyError):
                pass

        anomalies = []
        for cat, entries in by_cat.items():
            by_month: Dict[str, float] = defaultdict(float)
            for month, amount in entries:
                by_month[month] += amount
            if len(by_month) < 2:
                continue
            monthly = list(by_month.values())
            mean_m = statistics.mean(monthly)
            std_m = statistics.stdev(monthly) if len(monthly) > 1 else 0
            latest_month = max(by_month.keys())
            latest_amount = by_month[latest_month]
            z = (latest_amount - mean_m) / std_m if std_m > 0 else 0
            if z > self.ZSCORE_THRESHOLD:
                anomalies.append({
                    "id": str(uuid.uuid4()),
                    "transaction_id": None,
                    "anomaly_type": "category_spike",
                    "severity": "medium",
                    "score": round(min(z, 10), 2),
                    "description": f"Category '{cat}' spending spiked in {latest_month}: {latest_amount:.2f} (avg: {mean_m:.2f})",
                    "category": cat,
                    "month": latest_month,
                    "amount": round(latest_amount, 2),
                    "historical_avg": round(mean_m, 2),
                })
        return anomalies

    def _get_recent_transactions(self, user_id: str, days: int) -> List[Dict]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = []
        for t in _transactions.get(user_id, []):
            try:
                d = datetime.fromisoformat(t["date"])
                if d >= cutoff:
                    result.append(t)
            except (ValueError, KeyError):
                pass
        return result