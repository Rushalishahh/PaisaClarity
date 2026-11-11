"""create accounts categories and transactions

Revision ID: e8b1c4f2a9d0
Revises: c3f9a1d2b7e4
Create Date: 2026-11-11 20:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b1c4f2a9d0'
down_revision: Union[str, Sequence[str], None] = 'c3f9a1d2b7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create financial_accounts table
    op.create_table(
        'financial_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('account_type', sa.String(length=50), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('opening_balance', sa.Numeric(precision=14, scale=2), server_default='0.00', nullable=False),
        sa.Column('account_number_mask', sa.String(length=20), nullable=True),
        sa.Column('institution_name', sa.String(length=100), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('is_reconciled', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_financial_accounts_user_name')
    )
    op.create_index(op.f('ix_financial_accounts_id'), 'financial_accounts', ['id'], unique=False)
    op.create_index(op.f('ix_financial_accounts_user_id'), 'financial_accounts', ['user_id'], unique=False)
    op.create_index(op.f('ix_financial_accounts_is_archived'), 'financial_accounts', ['is_archived'], unique=False)

    # 2. Create categories table
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category_type', sa.String(length=50), server_default='expense', nullable=False),
        sa.Column('is_system', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)
    op.create_index(op.f('ix_categories_is_system'), 'categories', ['is_system'], unique=False)
    op.create_index('ix_categories_user_name', 'categories', ['user_id', 'name'], unique=False)

    # 3. Seed standard system categories
    categories_table = sa.table(
        'categories',
        sa.column('name', sa.String),
        sa.column('category_type', sa.String),
        sa.column('is_system', sa.Boolean),
        sa.column('user_id', sa.Integer),
        sa.column('created_at', sa.DateTime),
    )
    now_dt = datetime.now(timezone.utc)
    op.bulk_insert(
        categories_table,
        [
            {"name": "Income", "category_type": "income", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Investments", "category_type": "investment", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Transfers", "category_type": "transfer", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Rent", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "EMI & Loans", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Insurance", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Cash Withdrawal", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Food", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Groceries", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Shopping", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Transport", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Travel", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Bills", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Entertainment", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Health", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Education", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
            {"name": "Other", "category_type": "expense", "is_system": True, "user_id": None, "created_at": now_dt},
        ]
    )

    # 4. Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('statement_id', sa.Integer(), nullable=True),
        sa.Column('source_row_index', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('value_date', sa.Date(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('merchant', sa.String(length=200), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('classification', sa.String(length=20), server_default='expense', nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=100), server_default='Other', nullable=False),
        sa.Column('ref_no', sa.String(length=100), nullable=True),
        sa.Column('balance', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('transaction_key', sa.String(length=255), nullable=False),
        sa.Column('transfer_group_id', sa.String(length=36), nullable=True),
        sa.Column('import_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['statement_id'], ['statements.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('statement_id', 'source_row_index', name='uq_statement_source_row')
    )
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)
    op.create_index(op.f('ix_transactions_account_id'), 'transactions', ['account_id'], unique=False)
    op.create_index(op.f('ix_transactions_statement_id'), 'transactions', ['statement_id'], unique=False)
    op.create_index(op.f('ix_transactions_category_id'), 'transactions', ['category_id'], unique=False)
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)
    op.create_index(op.f('ix_transactions_ref_no'), 'transactions', ['ref_no'], unique=False)
    op.create_index(op.f('ix_transactions_transaction_key'), 'transactions', ['transaction_key'], unique=False)
    op.create_index(op.f('ix_transactions_transfer_group_id'), 'transactions', ['transfer_group_id'], unique=False)
    op.create_index('ix_transactions_user_date', 'transactions', ['user_id', 'date'], unique=False)
    op.create_index('ix_transactions_user_account', 'transactions', ['user_id', 'account_id'], unique=False)
    op.create_index('ix_transactions_user_category', 'transactions', ['user_id', 'category_id'], unique=False)
    op.create_index('ix_transactions_user_key', 'transactions', ['user_id', 'transaction_key'], unique=False)


def downgrade() -> None:
    # 1. Drop transactions table and indexes
    op.drop_index('ix_transactions_user_key', table_name='transactions')
    op.drop_index('ix_transactions_user_category', table_name='transactions')
    op.drop_index('ix_transactions_user_account', table_name='transactions')
    op.drop_index('ix_transactions_user_date', table_name='transactions')
    op.drop_index(op.f('ix_transactions_transfer_group_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_transaction_key'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_ref_no'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_category_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_statement_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_account_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_table('transactions')

    # 2. Drop categories table and indexes
    op.drop_index('ix_categories_user_name', table_name='categories')
    op.drop_index(op.f('ix_categories_is_system'), table_name='categories')
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_table('categories')

    # 3. Drop financial_accounts table and indexes
    op.drop_index(op.f('ix_financial_accounts_is_archived'), table_name='financial_accounts')
    op.drop_index(op.f('ix_financial_accounts_user_id'), table_name='financial_accounts')
    op.drop_index(op.f('ix_financial_accounts_id'), table_name='financial_accounts')
    op.drop_table('financial_accounts')
