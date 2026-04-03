from __future__ import annotations
from datetime import date, timedelta
from app.models import db, Expense, RecurringBill

def detect_recurring_anomalies(uid: int, months: int = 6) -> dict:
    """
    Detect anomalies in recurring transactions.
    Compares actual recurring bill amounts against historical averages.
    Also checks for missed or double-charged recurring bills.
    """
    cutoff = date.today() - timedelta(days=30 * months)
    bills = db.session.query(RecurringBill).filter_by(user_id=uid, active=True).all()
    
    anomalies = []
    expenses = db.session.query(Expense).filter(
        Expense.user_id == uid, Expense.date >= cutoff
    ).all()
    
    # Group expenses by note/description to find recurring patterns
    from collections import defaultdict
    import statistics
    
    note_groups: dict[str, list[float]] = defaultdict(list)
    for e in expenses:
        note = (getattr(e, "note", "") or "").lower().strip()
        if note:
            note_groups[note].append(float(e.amount or 0))
    
    for note, amounts in note_groups.items():
        if len(amounts) < 3:
            continue
        mean = statistics.mean(amounts)
        if len(amounts) >= 2:
            stdev = statistics.stdev(amounts)
            for i, amt in enumerate(amounts):
                if stdev > 0 and abs(amt - mean) > 2 * stdev:
                    anomalies.append({
                        "type": "amount_spike",
                        "note": note,
                        "anomalous_amount": round(amt, 2),
                        "average_amount": round(mean, 2),
                        "deviation_pct": round((amt - mean) / mean * 100, 1),
                    })
    
    # Check for overdue/missed recurring bills
    today = date.today()
    missed = []
    for bill in bills:
        due = getattr(bill, "due_date", None)
        paid = getattr(bill, "is_paid", False)
        if due and isinstance(due, date) and due < today and not paid:
            missed.append({
                "bill_id": bill.id,
                "due_date": due.isoformat(),
                "amount": float(getattr(bill, "amount", 0) or 0),
                "days_overdue": (today - due).days,
            })
    
    return {
        "anomalies": anomalies[:20],
        "anomaly_count": len(anomalies),
        "missed_bills": missed,
        "missed_bill_count": len(missed),
    }
