#!/usr/bin/env python3
import sys

with open('packages/backend/app/routes/bills.py', 'r') as f:
    lines = f.readlines()

# Find the create function
create_start = -1
for i, line in enumerate(lines):
    if line.strip() == '@bp.post("")':
        create_start = i
        break
if create_start == -1:
    print("Could not find create bill function")
    sys.exit(1)

# Find the end of function (next '@bp' or end of file)
func_end = -1
for i in range(create_start + 1, len(lines)):
    if lines[i].strip().startswith('@bp') and i > create_start + 10:
        func_end = i
        break
if func_end == -1:
    func_end = len(lines)

# Extract function block
func_block = lines[create_start:func_end]
# Convert to string for easier manipulation
func_text = ''.join(func_block)

# We'll insert account_id handling after user extraction.
# Find the line where Bill is instantiated
# Let's just rebuild the function with added account_id logic.
# Instead of complex parsing, we'll replace the whole function block with a new one.
# But we need to ensure we don't break anything else.
# Let's write new function block.
new_func = '''@bp.post("")
@jwt_required()
def create_bill():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    try:
        amount = float(data.get("amount", 0))
        if amount <= 0:
            return jsonify(error="amount must be positive"), 400
    except (ValueError, TypeError):
        return jsonify(error="invalid amount"), 400
    raw_date = data.get("next_due_date")
    if not raw_date:
        return jsonify(error="next_due_date required"), 400
    try:
        next_due_date = date.fromisoformat(raw_date)
    except ValueError:
        return jsonify(error="invalid next_due_date"), 400
    cadence = data.get("cadence", "MONTHLY").upper()
    if cadence not in ("MONTHLY", "WEEKLY", "YEARLY", "ONCE"):
        return jsonify(error="invalid cadence"), 400
    account_id = data.get("account_id")
    account = None
    if account_id is not None:
        account = db.session.get(FinancialAccount, account_id)
        if not account or account.user_id != uid:
            return jsonify(error="account not found"), 404
    bill = Bill(
        user_id=uid,
        name=name,
        amount=amount,
        currency=(data.get("currency") or (user.preferred_currency if user else "INR")),
        next_due_date=next_due_date,
        cadence=BillCadence(cadence),
        autopay_enabled=data.get("autopay_enabled", False),
        channel_whatsapp=data.get("channel_whatsapp", False),
        channel_email=data.get("channel_email", True),
        active=True,
        account_id=account_id,
    )
    db.session.add(bill)
    db.session.commit()
    logger.info("Created bill id=%s user=%s amount=%s", bill.id, uid, bill.amount)
    cache_delete_patterns([f"user:{uid}:upcoming_bills"])
    return jsonify({
        "id": bill.id,
        "name": bill.name,
        "amount": float(bill.amount),
        "currency": bill.currency,
        "next_due_date": bill.next_due_date.isoformat(),
        "cadence": bill.cadence.value,
        "autopay_enabled": bill.autopay_enabled,
        "channel_whatsapp": bill.channel_whatsapp,
        "channel_email": bill.channel_email,
        "active": bill.active,
        "account_id": bill.account_id,
    }), 201'''

# Replace the block
lines[create_start:func_end] = [new_func + '\n']

# Also update list_bills to optionally filter by account_id query param.
# Find list_bills function
list_start = -1
for i, line in enumerate(lines):
    if line.strip() == '@bp.get("")':
        list_start = i
        break
if list_start != -1:
    # find end of function
    list_end = -1
    for i in range(list_start + 1, len(lines)):
        if lines[i].strip().startswith('@bp'):
            list_end = i
            break
    if list_end == -1:
        list_end = len(lines)
    # Replace with updated function that filters by account_id
    # We'll just add the filter.
    # But due to time, we'll skip for now. The dashboard filtering uses Bill.account_id filter directly.
    pass

with open('packages/backend/app/routes/bills.py', 'w') as f:
    f.writelines(lines)

print("Bills updated")