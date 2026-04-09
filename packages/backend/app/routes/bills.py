from datetime import date

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Api, Resource
from marshmallow import ValidationError

from app.extensions import db
from app.models import Bill, Category, User
from app.schemas import BillSchema

bills_bp = Blueprint("bills", __name__, url_prefix="/bills")
api = Api(bills_bp)

bill_schema = BillSchema()
bills_schema = BillSchema(many=True)


class BillListResource(Resource):
    @jwt_required()
    def get(self):
        """
        List all bills for the authenticated user.
        """
        user_id = get_jwt_identity()
        bills = Bill.query.filter_by(user_id=user_id).all()
        return bills_schema.dump(bills), 200

    @jwt_required()
    def post(self):
        """
        Create a new bill for the authenticated user.
        Includes a category_id field to link to a category.
        """
        user_id = get_jwt_identity()
        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400

        try:
            data = bill_schema.load(json_data)
        except ValidationError as err:
            return err.messages, 400

        # Ensure currency defaults to user's preferred currency if not provided
        if "currency" not in data:
            user = User.query.get(user_id)
            if user:
                data["currency"] = user.preferred_currency
            else:
                # Fallback if user somehow not found (shouldn't happen with jwt_required)
                data["currency"] = "INR" # Default fallback

        # Validate category_id if provided
        if "category_id" in data and data["category_id"] is not None:
            category = Category.query.filter_by(user_id=user_id, id=data["category_id"]).first()
            if not category:
                return {"message": "Category not found."}, 404

        bill = Bill(user_id=user_id, **data)
        db.session.add(bill)
        db.session.commit()
        return bill_schema.dump(bill), 201


class BillResource(Resource):
    @jwt_required()
    def get(self, bill_id):
        """
        Retrieve a single bill for the authenticated user.
        """
        user_id = get_jwt_identity()
        bill = Bill.query.filter_by(user_id=user_id, id=bill_id).first()
        if not bill:
            return {"message": "Bill not found."}, 404
        return bill_schema.dump(bill), 200

    @jwt_required()
    def patch(self, bill_id):
        """
        Update an existing bill for the authenticated user.
        Allows updating category_id.
        """
        user_id = get_jwt_identity()
        bill = Bill.query.filter_by(user_id=user_id, id=bill_id).first()
        if not bill:
            return {"message": "Bill not found."}, 404

        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400

        try:
            data = bill_schema.load(json_data, partial=True)
        except ValidationError as err:
            return err.messages, 400

        # Validate category_id if provided and not None
        if "category_id" in data and data["category_id"] is not None:
            category = Category.query.filter_by(user_id=user_id, id=data["category_id"]).first()
            if not category:
                return {"message": "Category not found."}, 404
        elif "category_id" in data and data["category_id"] is None:
            # Explicitly allow unsetting category by sending category_id: null
            pass

        for key, value in data.items():
            setattr(bill, key, value)

        db.session.commit()
        return bill_schema.dump(bill), 200

    @jwt_required()
    def delete(self, bill_id):
        """
        Delete a bill for the authenticated user.
        """
        user_id = get_jwt_identity()
        bill = Bill.query.filter_by(user_id=user_id, id=bill_id).first()
        if not bill:
            return {"message": "Bill not found."}, 404

        db.session.delete(bill)
        db.session.commit()
        return {"message": "Bill deleted."}, 200


@bills_bp.route("/<uuid:bill_id>/pay", methods=["POST"])
@jwt_required()
def mark_bill_paid(bill_id):
    """
    Mark a bill as paid.
    """
    user_id = get_jwt_identity()
    bill = Bill.query.filter_by(user_id=user_id, id=bill_id).first()
    if not bill:
        return {"message": "Bill not found."}, 404

    bill.paid_date = date.today()
    db.session.commit()
    return {"message": "updated"}, 200


api.add_resource(BillListResource, "/")
api.add_resource(BillResource, "/<uuid:bill_id>")

