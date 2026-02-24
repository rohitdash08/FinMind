"""Add composite performance indexes for financial queries

Revision ID: a1b2c3d4e5f6
Revises: None
Create Date: 2026-02-24

This migration adds composite indexes targeting all high-frequency query
patterns in FinMind. Zero application-logic changes — purely additive
performance improvement.
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- expenses ---
    op.create_index('ix_expense_user_date', 'expenses', ['user_id', 'spent_at'])
    op.create_index('ix_expense_user_currency', 'expenses', ['user_id', 'currency'])
    op.create_index('ix_expense_user_category', 'expenses', ['user_id', 'category_id'])
    op.create_index('ix_expense_user_type', 'expenses', ['user_id', 'expense_type'])
    op.create_index('ix_expense_created', 'expenses', ['created_at'])

    # --- recurring_expenses ---
    op.create_index('ix_recurring_user_active', 'recurring_expenses', ['user_id', 'active'])
    op.create_index('ix_recurring_user_dates', 'recurring_expenses', ['user_id', 'start_date', 'end_date'])

    # --- bills ---
    op.create_index('ix_bill_user_due', 'bills', ['user_id', 'next_due_date'])
    op.create_index('ix_bill_user_active', 'bills', ['user_id', 'active'])

    # --- reminders ---
    op.create_index('ix_reminder_user_send_at', 'reminders', ['user_id', 'send_at'])
    op.create_index('ix_reminder_unsent', 'reminders', ['user_id', 'sent', 'send_at'])

    # --- categories ---
    op.create_index('ix_category_user', 'categories', ['user_id'])

    # --- audit_logs ---
    op.create_index('ix_audit_user_created', 'audit_logs', ['user_id', 'created_at'])

    # --- ad_impressions ---
    op.create_index('ix_ad_user_created', 'ad_impressions', ['user_id', 'created_at'])

    # --- user_subscriptions ---
    op.create_index('ix_subscription_user_active', 'user_subscriptions', ['user_id', 'active'])


def downgrade():
    # --- user_subscriptions ---
    op.drop_index('ix_subscription_user_active', table_name='user_subscriptions')

    # --- ad_impressions ---
    op.drop_index('ix_ad_user_created', table_name='ad_impressions')

    # --- audit_logs ---
    op.drop_index('ix_audit_user_created', table_name='audit_logs')

    # --- categories ---
    op.drop_index('ix_category_user', table_name='categories')

    # --- reminders ---
    op.drop_index('ix_reminder_unsent', table_name='reminders')
    op.drop_index('ix_reminder_user_send_at', table_name='reminders')

    # --- bills ---
    op.drop_index('ix_bill_user_active', table_name='bills')
    op.drop_index('ix_bill_user_due', table_name='bills')

    # --- recurring_expenses ---
    op.drop_index('ix_recurring_user_dates', table_name='recurring_expenses')
    op.drop_index('ix_recurring_user_active', table_name='recurring_expenses')

    # --- expenses ---
    op.drop_index('ix_expense_created', table_name='expenses')
    op.drop_index('ix_expense_user_type', table_name='expenses')
    op.drop_index('ix_expense_user_category', table_name='expenses')
    op.drop_index('ix_expense_user_currency', table_name='expenses')
    op.drop_index('ix_expense_user_date', table_name='expenses')
