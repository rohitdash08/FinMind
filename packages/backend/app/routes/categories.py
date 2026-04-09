import calendar
from datetime import date, timedelta

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Api, Resource
from marshmallow import ValidationError
from sqlalchemy import func

from app.extensions import db
from app.models import Bill, Category, User
from app.schemas import CategorySchema

categories_bp = Blueprint("categories", __name__, url_prefix="/categories")
api = Api(categories_bp)

category_schema = CategorySchema()
categories_schema = CategorySchema(many=True)


class CategoryListResource(Resource):
    @jwt_required()
    def get(self):
        """
        List all categories for the authenticated user, including current month's spend.
        """
        user_id = get_jwt_identity()
        categories = Category.query.filter_by(user_id=user_id).all()

        today = date.today()
        start_of_month = today.replace(day=1)
        # Get the last day of the current month
        _, last_day = calendar.monthrange(today.year, today.month)
        end_of_month = today.replace(day=last_day)

        for category in categories:
            # Sum amounts of bills for this category within the current month.
            # Only bills with a currency matching the category's budget currency are included
            # in the spend calculation if a budget currency is set.
            query = db.session.query(func.sum(Bill.amount)).filter(
                Bill.user_id == user_id,
                Bill.category_id == category.id,
                Bill.next_due_date >= start_of_month,
                Bill.next_due_date <= end_of_month,
            )
            if category.budget_currency:
                query = query.filter(Bill.currency == category.budget_currency)

            current_month_spend = query.scalar()
            # Assign the calculated spend to a transient attribute for serialization
            setattr(category, 'current_month_spend', current_month_spend if current_month_spend else 0.0)

        return categories_schema.dump(categories), 200

    @jwt_required()
    def post(self):
        """
        Create a new category for the authenticated user.
        Includes budget and budget_currency fields.
        """
        user_id = get_jwt_identity()
        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400

        try:
            data = category_schema.load(json_data)
        except ValidationError as err:
            return err.messages, 400

        # Check for duplicate name for the same user
        if Category.query.filter_by(user_id=user_id, name=data["name"]).first():
            return {"message": "Category with this name already exists."}, 409

        # Set default budget_currency if not provided
        if "budget_currency" not in data or data["budget_currency"] is None:
            user = User.query.get(user_id)
            if user:
                data["budget_currency"] = user.preferred_currency
            else:
                # Fallback if user somehow not found (shouldn't happen with jwt_required)
                data["budget_currency"] = "INR" # Default fallback

        category = Category(user_id=user_id, **data)
        db.session.add(category)
        db.session.commit()
        return category_schema.dump(category), 201


class CategoryResource(Resource):
    @jwt_required()
    def get(self, category_id):
        """
        Retrieve a single category for the authenticated user, including current month's spend.
        """
        user_id = get_jwt_identity()
        category = Category.query.filter_by(user_id=user_id, id=category_id).first()
        if not category:
            return {"message": "Category not found."}, 404

        today = date.today()
        start_of_month = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        end_of_month = today.replace(day=last_day)

        query = db.session.query(func.sum(Bill.amount)).filter(
            Bill.user_id == user_id,
            Bill.category_id == category.id,
            Bill.next_due_date >= start_of_month,
            Bill.next_due_date <= end_of_month,
        )
        if category.budget_currency:
            query = query.filter(Bill.currency == category.budget_currency)
        
        current_month_spend = query.scalar()
        setattr(category, 'current_month_spend', current_month_spend if current_month_spend else 0.0)

        return category_schema.dump(category), 200

    @jwt_required()
    def patch(self, category_id):
        """
        Update an existing category for the authenticated user.
        Allows updating budget and budget_currency.
        """
        user_id = get_jwt_identity()
        category = Category.query.filter_by(user_id=user_id, id=category_id).first()
        if not category:
            return {"message": "Category not found."}, 404

        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400

        try:
            # partial=True allows sending only fields to be updated
            data = category_schema.load(json_data, partial=True)
        except ValidationError as err:
            return err.messages, 400

        # Check for duplicate name if name is being updated
        if "name" in data and data["name"] != category.name:
            if Category.query.filter_by(user_id=user_id, name=data["name"]).first():
                return {"message": "Category with this name already exists."}, 409

        for key, value in data.items():
            setattr(category, key, value)

        db.session.commit()
        return category_schema.dump(category), 200

    @jwt_required()
    def delete(self, category_id):
        """
        Delete a category for the authenticated user.
        Bills previously linked to this category will have their category_id set to NULL.
        """
        user_id = get_jwt_identity()
        category = Category.query.filter_by(user_id=user_id, id=category_id).first()
        if not category:
            return {"message": "Category not found."}, 404

        # Disassociate bills from this category before deleting the category
        # Using synchronize_session='fetch' to ensure relationships are properly handled
        Bill.query.filter_by(category_id=category_id, user_id=user_id).update(
            {"category_id": None}, synchronize_session="fetch"
        )
        db.session.delete(category)
        db.session.commit()
        return {"message": "Category deleted."}, 200


api.add_resource(CategoryListResource, "/")
api.add_resource(CategoryResource, "/<uuid:category_id>")

