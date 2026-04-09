import pytest
from flask import Blueprint, jsonify, request, g
from io import StringIO
import csv
from datetime import date
import re
from decimal import Decimal, InvalidOperation

# Assuming app.models and app.extensions exist as set up by conftest.py
# We'll use them here for database interactions in tests.
from app.extensions import db
from app.models import Bill, Category, User


# Sample CSV data for testing various scenarios
_BULK_BILL_IMPORT_SAMPLE_CSV = """name,amount,next_due_date,cadence,channel_email,channel_whatsapp,autopay_enabled,currency,category_name
Internet,49.99,2024-03-20,MONTHLY,true,false,false,USD,Utilities
Rent,1200,2024-04-01,MONTHLY,true,false,true,,Housing
Groceries,150.5,2024-03-25,WEEKLY,false,true,false,EUR,Food
Electricity,75,2024-03-10,MONTHLY,,,false,GBP,Utilities
Bad Date,,2024-03-30,DAILY,,,,Other
Invalid Cadence,20.0,2024-05-01,INVALID,true,,,USD,Misc
Negative Amount,-10.0,2024-06-01,MONTHLY,,,USD,Other
Missing Name,,25.0,2024-07-01,MONTHLY,,,USD,Other
Duplicate Bill,50.0,2024-08-01,MONTHLY,,,USD,Utilities
Duplicate Bill,50.0,2024-08-01,MONTHLY,,,USD,Utilities
Future Category Bill,30.0,2024-09-01,MONTHLY,,,USD,New Category
"""

# Valid cadences
VALID_CADENCES = ["DAILY", "WEEKLY", "BI_WEEKLY", "MONTHLY", "QUARTERLY", "ANNUALLY"]

def _parse_boolean_field(value):
    """Parses a string value into a boolean."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False # Default to false for optional bool fields
    value = str(value).strip().lower()
    return value in ['true', '1', 'yes']

def _process_csv_data(csv_data: str, user_id: int, preferred_currency: str):
    """
    Simulates the backend logic for validating and previewing bill import data.
    This function processes CSV content, validates each row, applies defaults,
    and generates a preview with warnings/errors.
    """
    reader = csv.DictReader(StringIO(csv_data))
    
    preview_items = []
    row_details = []
    
    total_rows = 0
    valid_rows = 0
    rows_with_warnings = 0
    rows_with_errors = 0

    # Cache existing categories for this user for validation
    existing_categories = {
        c.name.lower(): c.id
        for c in db.session.execute(
            db.select(Category).filter_by(user_id=user_id)
        ).scalars().all()
    }
    
    for i, row in enumerate(reader):
        total_rows += 1
        row_number = i + 1  # 1-based index for user display
        messages = []
        status = "valid"
        processed_data = {
            "user_id": user_id,
            "currency": preferred_currency # Default currency
        }

        # --- Required Field Validations ---
        name = row.get("name", "").strip()
        if not name:
            messages.append("Error: 'name' is a required field.")
            status = "error"
        else:
            processed_data["name"] = name
        
        amount_str = row.get("amount", "").strip()
        if not amount_str:
            messages.append("Error: 'amount' is a required field.")
            status = "error"
        else:
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    messages.append("Error: 'amount' must be a positive number.")
                    status = "error"
                else:
                    # Correct to 2 decimal places
                    corrected_amount = amount.quantize(Decimal('0.01'))
                    if corrected_amount != amount:
                        messages.append(f"Warning: 'amount' corrected from {amount} to {corrected_amount}.")
                        if status != "error": status = "warning"
                    processed_data["amount"] = corrected_amount
            except InvalidOperation:
                messages.append(f"Error: 'amount' '{amount_str}' is not a valid number.")
                status = "error"

        next_due_date_str = row.get("next_due_date", "").strip()
        if not next_due_date_str:
            messages.append("Error: 'next_due_date' is a required field.")
            status = "error"
        else:
            try:
                processed_data["next_due_date"] = date.fromisoformat(next_due_date_str)
            except ValueError:
                messages.append(f"Error: 'next_due_date' '{next_due_date_str}' is not a valid ISO date (YYYY-MM-DD).")
                status = "error"

        cadence = row.get("cadence", "").strip().upper()
        if not cadence:
            messages.append("Error: 'cadence' is a required field.")
            status = "error"
        elif cadence not in VALID_CADENCES:
            messages.append(f"Error: 'cadence' '{cadence}' is not valid. Must be one of {', '.join(VALID_CADENCES)}.")
            status = "error"
        else:
            processed_data["cadence"] = cadence

        # --- Optional Field Validations and Defaults ---
        processed_data["channel_email"] = _parse_boolean_field(row.get("channel_email"))
        processed_data["channel_whatsapp"] = _parse_boolean_field(row.get("channel_whatsapp"))
        processed_data["autopay_enabled"] = _parse_boolean_field(row.get("autopay_enabled"))

        # Currency
        if row.get("currency"):
            currency = row["currency"].strip().upper()
            # Basic ISO 4217 validation for 3 uppercase letters
            if not re.fullmatch(r"^[A-Z]{3}$", currency):
                messages.append(f"Warning: 'currency' '{currency}' is not a valid 3-letter ISO code. Defaulting to preferred currency {preferred_currency}.")
                if status == "valid": status = "warning"
            else:
                processed_data["currency"] = currency
        
        # Category
        category_name = row.get("category_name", "").strip()
        if category_name:
            processed_data["category_name"] = category_name # Keep for display in preview
            if category_name.lower() not in existing_categories:
                messages.append(f"Warning: Category '{category_name}' does not exist and will be created upon import.")
                if status == "valid": status = "warning"
            else:
                processed_data["category_id"] = existing_categories[category_name.lower()]

        # Mark as warning if no errors but messages exist
        if status == "valid" and messages:
            status = "warning"

        # Update summary counts
        if status == "error":
            rows_with_errors += 1
        elif status == "warning":
            rows_with_warnings += 1
        else:
            valid_rows += 1
        
        row_details.append({
            "row_number": row_number,
            "status": status,
            "messages": messages,
            "data": {k: str(v) for k, v in processed_data.items()} # Convert date/decimal to string for JSON preview
        })
        preview_items.append(processed_data) # Keep original types for potential next step import

    # Filter out rows with errors for the main preview_items list
    final_preview_items = [item for item, detail in zip(preview_items, row_details) if detail["status"] != "error"]

    return {
        "preview_items": [{k: str(v) for k,v in item.items()} for item in final_preview_items], # Convert to string for JSON
        "validation_summary": {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "rows_with_warnings": rows_with_warnings,
            "rows_with_errors": rows_with_errors
        },
        "row_details": row_details
    }


def test_bulk_bill_import_preview(client, auth_header):
    """
    Tests the bulk bill import preview functionality.
    This test sets up a temporary endpoint within the test application to
    simulate the actual backend /bills/import/preview route.
    It verifies data parsing, validation, default application, and error reporting.
    """
    app = client.application

    # Create a dummy blueprint and add our temporary route
    temp_bp = Blueprint("temp_bulk_import", __name__)

    @temp_bp.route("/bills/import/preview", methods=["POST"])
    def temp_bulk_import_preview():
        """
        Simulated endpoint for bulk bill import preview.
        In a real application, g.user would be populated by @jwt_required().
        """
        csv_data = request.data.decode('utf-8')
        
        # Get user details for preferred currency and user_id
        # In a real app, g.user would be available after @jwt_required()
        # For this test, we mimic fetching it via /auth/me
        user_info = client.get("/auth/me", headers=auth_header).get_json()
        user_id = user_info["id"]
        preferred_currency = user_info["preferred_currency"]

        # Call the core processing logic
        result = _process_csv_data(csv_data, user_id, preferred_currency)
        return jsonify(result), 200

    app.register_blueprint(temp_bp)

    # --- Setup: Create a user category and update preferred currency for testing ---
    user_info = client.get("/auth/me", headers=auth_header).get_json()
    test_user_id = user_info["id"]

    # Update preferred currency for the user
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200
    user_info = r.get_json()
    assert user_info["preferred_currency"] == "EUR"
    
    # Create an existing category for the user
    r = client.post("/categories", json={"name": "Utilities"}, headers=auth_header)
    assert r.status_code in (201, 409) # 409 if already exists from previous test run

    # --- Perform the bulk import preview request ---
    r = client.post(
        "/bills/import/preview",
        data=_BULK_BILL_IMPORT_SAMPLE_CSV,
        content_type="text/csv",
        headers=auth_header
    )
    assert r.status_code == 200
    response_data = r.get_json()

    # --- Assertions for the overall summary ---
    summary = response_data["validation_summary"]
    assert summary["total_rows"] == 11
    assert summary["valid_rows"] == 2 # Internet, Rent
    assert summary["rows_with_warnings"] == 4 # Groceries, Electricity, Duplicate Bill (x2)
    assert summary["rows_with_errors"] == 5 # Bad Date, Invalid Cadence, Negative Amount, Missing Name, Duplicate Bill (1st of 2 bad names)

    # --- Assertions for specific row details and preview items ---
    row_details = response_data["row_details"]
    preview_items = response_data["preview_items"]

    # Row 1: Internet (Valid)
    # name,amount,next_due_date,cadence,channel_email,channel_whatsapp,autopay_enabled,currency,category_name
    # Internet,49.99,2024-03-20,MONTHLY,true,false,false,USD,Utilities
    assert row_details[0]["row_number"] == 1
    assert row_details[0]["status"] == "valid"
    assert "Internet" in preview_items[0]["name"]
    assert preview_items[0]["amount"] == "49.99"
    assert preview_items[0]["currency"] == "USD"
    assert preview_items[0]["category_name"] == "Utilities"

    # Row 2: Rent (Uses user's preferred currency, which is EUR from setup)
    # Rent,1200,2024-04-01,MONTHLY,true,false,true,,Housing
    assert row_details[1]["row_number"] == 2
    assert row_details[1]["status"] == "valid"
    assert preview_items[1]["name"] == "Rent"
    assert preview_items[1]["amount"] == "1200.00" # Corrected to 2 decimal places
    assert preview_items[1]["currency"] == "EUR" # Defaulted to user's preferred
    assert "Housing" in preview_items[1]["category_name"]

    # Row 3: Groceries (Warning - Amount corrected, currency changed, category new)
    # Groceries,150.5,2024-03-25,WEEKLY,false,true,false,EUR,Food
    assert row_details[2]["row_number"] == 3
    assert row_details[2]["status"] == "warning"
    assert "Amount corrected from 150.5 to 150.50" in row_details[2]["messages"][0]
    assert "Category 'Food' does not exist" in row_details[2]["messages"][1]
    assert preview_items[2]["amount"] == "150.50"
    assert preview_items[2]["currency"] == "EUR"
    assert preview_items[2]["category_name"] == "Food"

    # Row 4: Electricity (Warning - missing bool defaults, currency valid but not preferred)
    # Electricity,75,2024-03-10,MONTHLY,,,false,GBP,Utilities
    assert row_details[3]["row_number"] == 4
    assert row_details[3]["status"] == "warning"
    assert "Amount corrected from 75 to 75.00" in row_details[3]["messages"][0]
    assert preview_items[3]["amount"] == "75.00"
    assert preview_items[3]["currency"] == "GBP" # Explicitly provided, not defaulted
    assert preview_items[3]["channel_email"] == "False" # Defaulted
    assert preview_items[3]["channel_whatsapp"] == "False" # Defaulted
    assert preview_items[3]["autopay_enabled"] == "False"
    assert preview_items[3]["category_name"] == "Utilities" # Existing category

    # Row 5: Bad Date (Error: missing amount, invalid date)
    # Bad Date,,2024-03-30,DAILY,,,,Other
    assert row_details[4]["row_number"] == 5
    assert row_details[4]["status"] == "error"
    assert "Error: 'amount' is a required field." in row_details[4]["messages"]
    # Should not be in preview_items because it has errors
    assert not any(item["name"] == "Bad Date" for item in preview_items)

    # Row 6: Invalid Cadence (Error)
    # Invalid Cadence,20.0,2024-05-01,INVALID,true,,,USD,Misc
    assert row_details[5]["row_number"] == 6
    assert row_details[5]["status"] == "error"
    assert "Error: 'cadence' 'INVALID' is not valid." in row_details[5]["messages"][0]

    # Row 7: Negative Amount (Error)
    # Negative Amount,-10.0,2024-06-01,MONTHLY,,,USD,Other
    assert row_details[6]["row_number"] == 7
    assert row_details[6]["status"] == "error"
    assert "Error: 'amount' must be a positive number." in row_details[6]["messages"][0]

    # Row 8: Missing Name (Error)
    # Missing Name,,25.0,2024-07-01,MONTHLY,,,USD,Other
    assert row_details[7]["row_number"] == 8
    assert row_details[7]["status"] == "error"
    assert "Error: 'name' is a required field." in row_details[7]["messages"][0]
    assert "Error: 'amount' is a required field." in row_details[7]["messages"][1]

    # Row 9 & 10: Duplicate Bill (Warnings)
    # Duplicate Bill,50.0,2024-08-01,MONTHLY,,,USD,Utilities
    assert row_details[8]["row_number"] == 9
    assert row_details[8]["status"] == "warning"
    assert "Amount corrected from 50 to 50.00" in row_details[8]["messages"][0]
    assert preview_items[4]["name"] == "Duplicate Bill"

    assert row_details[9]["row_number"] == 10
    assert row_details[9]["status"] == "warning"
    assert "Amount corrected from 50 to 50.00" in row_details[9]["messages"][0]
    assert preview_items[5]["name"] == "Duplicate Bill"

    # Row 11: Future Category Bill (Warning)
    # Future Category Bill,30.0,2024-09-01,MONTHLY,,,USD,New Category
    assert row_details[10]["row_number"] == 11
    assert row_details[10]["status"] == "warning"
    assert "Category 'New Category' does not exist and will be created upon import." in row_details[10]["messages"][1]
    assert preview_items[6]["name"] == "Future Category Bill"
    assert preview_items[6]["currency"] == "USD"
    assert preview_items[6]["category_name"] == "New Category"
