"""
SQLAlchemy __table_args__ indexes applied directly to models.
These mirror 003_perf_indexes.py migration for ORM-level awareness.
Import this module to patch index definitions onto existing models.
"""
from sqlalchemy import Index
from .models import Expense, RecurringExpense, Bill, Category

# High-frequency query indexes
Index("ix_expenses_user_spent",     Expense.user_id,          Expense.spent_at)
Index("ix_expenses_user_category",  Expense.user_id,          Expense.category_id)
Index("ix_expenses_user_type",      Expense.user_id,          Expense.expense_type)
Index("ix_recurring_user_active",   RecurringExpense.user_id, RecurringExpense.active)
Index("ix_bills_user_due",          Bill.user_id,             Bill.due_date)
Index("ix_categories_user",         Category.user_id)
