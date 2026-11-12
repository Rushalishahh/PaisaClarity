"""create budgets and savings goals

Revision ID: f7a8b9c0d1e2
Revises: e8b1c4f2a9d0
Create Date: 2026-11-12 15:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e8b1c4f2a9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create budgets table
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('total_budget_limit', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('warning_threshold', sa.Numeric(precision=5, scale=2), server_default='80.00', nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'month', 'year', name='uq_budget_user_month_year')
    )
    op.create_index(op.f('ix_budgets_id'), 'budgets', ['id'], unique=False)
    op.create_index(op.f('ix_budgets_user_id'), 'budgets', ['user_id'], unique=False)
    op.create_index(op.f('ix_budgets_is_archived'), 'budgets', ['is_archived'], unique=False)
    op.create_index('ix_budgets_user_period', 'budgets', ['user_id', 'year', 'month'], unique=False)

    # 2. Create budget_allocations table
    op.create_table(
        'budget_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('category_name', sa.String(length=100), nullable=False),
        sa.Column('allocated_amount', sa.Numeric(precision=14, scale=2), server_default='0.00', nullable=False),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('budget_id', 'category_name', name='uq_budget_allocation_category')
    )
    op.create_index(op.f('ix_budget_allocations_id'), 'budget_allocations', ['id'], unique=False)
    op.create_index(op.f('ix_budget_allocations_budget_id'), 'budget_allocations', ['budget_id'], unique=False)
    op.create_index(op.f('ix_budget_allocations_category_id'), 'budget_allocations', ['category_id'], unique=False)

    # 3. Create savings_goals table
    op.create_table(
        'savings_goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('target_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_savings_goals_id'), 'savings_goals', ['id'], unique=False)
    op.create_index(op.f('ix_savings_goals_user_id'), 'savings_goals', ['user_id'], unique=False)
    op.create_index(op.f('ix_savings_goals_is_archived'), 'savings_goals', ['is_archived'], unique=False)
    op.create_index('ix_savings_goals_user', 'savings_goals', ['user_id', 'is_archived'], unique=False)

    # 4. Create savings_contributions table
    op.create_table(
        'savings_contributions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('goal_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('contribution_date', sa.Date(), nullable=False),
        sa.Column('contribution_type', sa.String(length=20), server_default='deposit', nullable=False),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['goal_id'], ['savings_goals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_savings_contributions_id'), 'savings_contributions', ['id'], unique=False)
    op.create_index(op.f('ix_savings_contributions_goal_id'), 'savings_contributions', ['goal_id'], unique=False)
    op.create_index(op.f('ix_savings_contributions_user_id'), 'savings_contributions', ['user_id'], unique=False)
    op.create_index('ix_savings_contributions_goal_date', 'savings_contributions', ['goal_id', 'contribution_date'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table('savings_contributions')
    op.drop_table('savings_goals')
    op.drop_table('budget_allocations')
    op.drop_table('budgets')

