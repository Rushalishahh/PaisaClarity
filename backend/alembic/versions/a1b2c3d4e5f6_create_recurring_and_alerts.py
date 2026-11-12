"""create recurring payments and financial alerts

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-11-12 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add alert_preferences column to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alert_preferences', sa.JSON(), nullable=True))

    # 2. Create recurring_payments table
    op.create_table(
        'recurring_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=100), server_default='Bills', nullable=False),
        sa.Column('average_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('frequency', sa.String(length=50), server_default='monthly', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='detected', nullable=False),
        sa.Column('next_expected_date', sa.Date(), nullable=True),
        sa.Column('last_payment_date', sa.Date(), nullable=True),
        sa.Column('first_seen_date', sa.Date(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_auto_detected', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recurring_payments_id'), 'recurring_payments', ['id'], unique=False)
    op.create_index(op.f('ix_recurring_payments_user_id'), 'recurring_payments', ['user_id'], unique=False)
    op.create_index(op.f('ix_recurring_payments_account_id'), 'recurring_payments', ['account_id'], unique=False)
    op.create_index('ix_recurring_user_status', 'recurring_payments', ['user_id', 'status'], unique=False)
    op.create_index('ix_recurring_user_next_date', 'recurring_payments', ['user_id', 'next_expected_date'], unique=False)

    # 3. Create financial_alerts table
    op.create_table(
        'financial_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='info', nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('related_entity_type', sa.String(length=50), nullable=True),
        sa.Column('related_entity_id', sa.Integer(), nullable=True),
        sa.Column('dedup_key', sa.String(length=255), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_dismissed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'dedup_key', name='uq_alert_user_dedup')
    )
    op.create_index(op.f('ix_financial_alerts_id'), 'financial_alerts', ['id'], unique=False)
    op.create_index(op.f('ix_financial_alerts_user_id'), 'financial_alerts', ['user_id'], unique=False)
    op.create_index(op.f('ix_financial_alerts_dedup_key'), 'financial_alerts', ['dedup_key'], unique=False)
    op.create_index(op.f('ix_financial_alerts_is_dismissed'), 'financial_alerts', ['is_dismissed'], unique=False)
    op.create_index('ix_alerts_user_unread', 'financial_alerts', ['user_id', 'is_dismissed', 'is_read'], unique=False)


def downgrade() -> None:
    # 1. Drop financial_alerts table
    op.drop_index('ix_alerts_user_unread', table_name='financial_alerts')
    op.drop_index(op.f('ix_financial_alerts_is_dismissed'), table_name='financial_alerts')
    op.drop_index(op.f('ix_financial_alerts_dedup_key'), table_name='financial_alerts')
    op.drop_index(op.f('ix_financial_alerts_user_id'), table_name='financial_alerts')
    op.drop_index(op.f('ix_financial_alerts_id'), table_name='financial_alerts')
    op.drop_table('financial_alerts')

    # 2. Drop recurring_payments table
    op.drop_index('ix_recurring_user_next_date', table_name='recurring_payments')
    op.drop_index('ix_recurring_user_status', table_name='recurring_payments')
    op.drop_index(op.f('ix_recurring_payments_account_id'), table_name='recurring_payments')
    op.drop_index(op.f('ix_recurring_payments_user_id'), table_name='recurring_payments')
    op.drop_index(op.f('ix_recurring_payments_id'), table_name='recurring_payments')
    op.drop_table('recurring_payments')

    # 3. Drop alert_preferences column from users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('alert_preferences')

