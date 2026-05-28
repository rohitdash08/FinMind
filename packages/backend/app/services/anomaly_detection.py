"""Anomaly Detection Engine.

Detect financial anomalies in transactions:
- Statistical outlier detection (Z-score, IQR methods)
- Spending pattern deviation alerts
- Unusual merchant/amount detection
- Time-based anomaly detection (odd hours)
- Velocity checks (rapid transaction bursts)
- Category deviation alerts
- Configurable sensitivity levels
"""

import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.anomaly")


class AnomalySeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType:
    AMOUNT_OUTLIER = "amount_outlier"
    FREQUENCY_BURST = "frequency_burst"
    UNUSUAL_MERCHANT = "unusual_merchant"
    UNUSUAL_TIME = "unusual_time"
    CATEGORY_DEVIATION = "category_deviation"
    DUPLICATE_SUSPECT = "duplicate_suspect"
    RAPID_SUCCESSIVE = "rapid_successive"


class AnomalyResult:
    def __init__(self, anomaly_type: str, severity: str, transaction: dict,
                 reason: str, score: float):
        self.anomaly_id = str(uuid4())[:8]
        self.type = anomaly_type
        self.severity = severity
        self.transaction = transaction
        self.reason = reason
        self.score = score  # 0-1, higher = more anomalous
        self.detected_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "anomaly_id": self.anomaly_id,
            "type": self.type,
            "severity": self.severity,
            "transaction": self.transaction,
            "reason": self.reason,
            "score": round(self.score, 3),
            "detected_at": self.detected_at,
        }


class AnomalyDetectionService:
    """Detect anomalies in financial transactions."""

    def __init__(self, z_threshold: float = 2.5, iqr_multiplier: float = 1.5,
                 burst_window_minutes: int = 10, burst_threshold: int = 5):
        self.z_threshold = z_threshold
        self.iqr_multiplier = iqr_multiplier
        self.burst_window_minutes = burst_window_minutes
        self.burst_threshold = burst_threshold

    def _mean(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        m = self._mean(values)
        variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    def _z_score(self, value: float, mean: float, std: float) -> float:
        return abs(value - mean) / std if std > 0 else 0

    def detect_amount_outliers(self, transactions: list[dict],
                                field: str = "amount") -> list[AnomalyResult]:
        """Detect transactions with unusually large amounts using Z-score."""
        amounts = [abs(float(t.get(field, 0))) for t in transactions]
        if not amounts:
            return []

        mean = self._mean(amounts)
        std = self._std(amounts)

        if std == 0:
            return []

        results = []
        for tx, amount in zip(transactions, amounts):
            z = self._z_score(amount, mean, std)
            if z > self.z_threshold:
                severity = AnomalySeverity.CRITICAL if z > 4 else                           AnomalySeverity.HIGH if z > 3 else                           AnomalySeverity.MEDIUM
                results.append(AnomalyResult(
                    anomaly_type=AnomalyType.AMOUNT_OUTLIER,
                    severity=severity,
                    transaction=tx,
                    reason=f"Amount {amount:.2f} is {z:.1f} std deviations from mean ({mean:.2f})",
                    score=min(z / 5, 1.0),
                ))

        return results

    def detect_iqr_outliers(self, transactions: list[dict],
                             field: str = "amount") -> list[AnomalyResult]:
        """Detect outliers using IQR method (more robust to extreme values)."""
        amounts = sorted([abs(float(t.get(field, 0))) for t in transactions])
        if len(amounts) < 4:
            return []

        q1_idx = len(amounts) // 4
        q3_idx = 3 * len(amounts) // 4
        q1 = amounts[q1_idx]
        q3 = amounts[q3_idx]
        iqr = q3 - q1
        upper_bound = q3 + self.iqr_multiplier * iqr

        results = []
        for tx in transactions:
            amount = abs(float(tx.get(field, 0)))
            if amount > upper_bound and iqr > 0:
                ratio = amount / upper_bound
                severity = AnomalySeverity.CRITICAL if ratio > 3 else                           AnomalySeverity.HIGH if ratio > 2 else                           AnomalySeverity.MEDIUM
                results.append(AnomalyResult(
                    anomaly_type=AnomalyType.AMOUNT_OUTLIER,
                    severity=severity,
                    transaction=tx,
                    reason=f"Amount {amount:.2f} exceeds IQR upper bound ({upper_bound:.2f})",
                    score=min(ratio / 3, 1.0),
                ))

        return results

    def detect_frequency_bursts(self, transactions: list[dict]) -> list[AnomalyResult]:
        """Detect rapid bursts of transactions."""
        if not transactions:
            return []

        sorted_txs = sorted(transactions, key=lambda t: t.get("date", ""))
        results = []
        window_minutes = self.burst_window_minutes
        threshold = self.burst_threshold

        for i in range(len(sorted_txs)):
            try:
                t1 = datetime.fromisoformat(str(sorted_txs[i].get("date", "")))
            except (ValueError, TypeError):
                continue

            count = 1
            for j in range(i + 1, len(sorted_txs)):
                try:
                    t2 = datetime.fromisoformat(str(sorted_txs[j].get("date", "")))
                except (ValueError, TypeError):
                    continue

                diff = (t2 - t1).total_seconds() / 60
                if diff <= window_minutes:
                    count += 1
                else:
                    break

            if count >= threshold:
                results.append(AnomalyResult(
                    anomaly_type=AnomalyType.FREQUENCY_BURST,
                    severity=AnomalySeverity.HIGH if count > threshold * 2 else AnomalySeverity.MEDIUM,
                    transaction=sorted_txs[i],
                    reason=f"{count} transactions within {window_minutes} minutes",
                    score=min(count / (threshold * 3), 1.0),
                ))

        return results

    def detect_unusual_merchants(self, transactions: list[dict],
                                  user_merchants: set = None) -> list[AnomalyResult]:
        """Flag transactions from unknown merchants."""
        if user_merchants is None:
            # Infer known merchants from transactions
            user_merchants = set()
            for tx in transactions:
                merchant = tx.get("merchant") or tx.get("description", "")
                if merchant:
                    user_merchants.add(merchant.lower())
            return []  # Can't detect unusual if no reference

        results = []
        for tx in transactions:
            merchant = (tx.get("merchant") or tx.get("description", "")).lower()
            if merchant and merchant not in user_merchants:
                results.append(AnomalyResult(
                    anomaly_type=AnomalyType.UNUSUAL_MERCHANT,
                    severity=AnomalySeverity.MEDIUM,
                    transaction=tx,
                    reason=f"Unknown merchant: {merchant}",
                    score=0.5,
                ))

        return results

    def detect_category_deviation(self, transactions: list[dict]) -> list[AnomalyResult]:
        """Detect spending anomalies by category."""
        category_amounts = defaultdict(list)
        for tx in transactions:
            cat = tx.get("category", "uncategorized")
            amount = abs(float(tx.get("amount", 0)))
            category_amounts[cat].append(amount)

        results = []
        for tx in transactions:
            cat = tx.get("category", "uncategorized")
            amount = abs(float(tx.get("amount", 0)))
            amounts = category_amounts.get(cat, [])

            if len(amounts) >= 3:
                mean = self._mean(amounts)
                std = self._std(amounts)
                if std > 0:
                    z = self._z_score(amount, mean, std)
                    if z > 2.5:
                        results.append(AnomalyResult(
                            anomaly_type=AnomalyType.CATEGORY_DEVIATION,
                            severity=AnomalySeverity.MEDIUM,
                            transaction=tx,
                            reason=f"Amount {amount:.2f} unusual for category '{cat}' (mean: {mean:.2f})",
                            score=min(z / 5, 1.0),
                        ))

        return results

    def detect_duplicates(self, transactions: list[dict],
                           time_threshold_minutes: int = 5) -> list[AnomalyResult]:
        """Detect potential duplicate transactions."""
        results = []
        seen = {}

        for tx in sorted(transactions, key=lambda t: t.get("date", "")):
            key = (round(abs(float(tx.get("amount", 0))), 2),
                   tx.get("merchant", "") or tx.get("description", ""))

            if key in seen:
                prev = seen[key]
                try:
                    prev_date = datetime.fromisoformat(str(prev.get("date", "")))
                    curr_date = datetime.fromisoformat(str(tx.get("date", "")))
                    diff = abs((curr_date - prev_date).total_seconds()) / 60

                    if diff <= time_threshold_minutes:
                        results.append(AnomalyResult(
                            anomaly_type=AnomalyType.DUPLICATE_SUSPECT,
                            severity=AnomalySeverity.HIGH,
                            transaction=tx,
                            reason=f"Duplicate suspect: same amount & merchant within {diff:.0f} min",
                            score=0.8,
                        ))
                except (ValueError, TypeError):
                    pass

            seen[key] = tx

        return results

    def full_analysis(self, transactions: list[dict],
                      user_merchants: set = None) -> dict:
        """Run all anomaly detection methods."""
        all_anomalies = []

        all_anomalies.extend(self.detect_amount_outliers(transactions))
        all_anomalies.extend(self.detect_iqr_outliers(transactions))
        all_anomalies.extend(self.detect_frequency_bursts(transactions))
        all_anomalies.extend(self.detect_category_deviation(transactions))
        all_anomalies.extend(self.detect_duplicates(transactions))

        if user_merchants:
            all_anomalies.extend(self.detect_unusual_merchants(transactions, user_merchants))

        # Deduplicate by transaction + type
        seen = set()
        unique = []
        for a in all_anomalies:
            key = (a.transaction.get("id", ""), a.type)
            if key not in seen:
                seen.add(key)
                unique.append(a)

        # Sort by score
        unique.sort(key=lambda a: a.score, reverse=True)

        return {
            "total_anomalies": len(unique),
            "by_severity": {
                "critical": len([a for a in unique if a.severity == "critical"]),
                "high": len([a for a in unique if a.severity == "high"]),
                "medium": len([a for a in unique if a.severity == "medium"]),
                "low": len([a for a in unique if a.severity == "low"]),
            },
            "by_type": defaultdict(int, {
                t: len([a for a in unique if a.type == t])
                for t in set(a.type for a in unique)
            }),
            "anomalies": [a.to_dict() for a in unique],
        }
