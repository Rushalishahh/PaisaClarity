"""create investments table

Revision ID: 70eb4e4a3876
Revises: a80c775079b1
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70eb4e4a3876'
down_revision: Union[str, Sequence[str], None] = 'a80c775079b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'investments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('investment_type', sa.String(), nullable=True),
        sa.Column('scheme_code', sa.String(), nullable=True),
        sa.Column('units', sa.Numeric(), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('premium_amount', sa.Numeric(), nullable=True),
        sa.Column('premium_frequency', sa.String(), nullable=True),
        sa.Column('next_due_date', sa.Date(), nullable=True),
        sa.Column('maturity_date', sa.Date(), nullable=True),
        sa.Column('maturity_value', sa.Numeric(), nullable=True),
        sa.Column('invested_amount', sa.Numeric(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_investments_id'), 'investments', ['id'], unique=False)
    op.create_index(op.f('ix_investments_user_id'), 'investments', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_investments_user_id'), table_name='investments')
    op.drop_index(op.f('ix_investments_id'), table_name='investments')
    op.drop_table('investments')