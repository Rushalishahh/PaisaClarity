"""add start_date to investments

Revision ID: c3f9a1d2b7e4
Revises: 70eb4e4a3876
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9a1d2b7e4'
down_revision: Union[str, Sequence[str], None] = '70eb4e4a3876'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the policy start_date column.

    Nullable: existing rows were created before this field existed and
    must keep working unchanged. New policy-category rows are required to
    provide it by the InvestmentCreate schema instead of by the database.
    """
    op.add_column(
        'investments',
        sa.Column('start_date', sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Remove the start_date column."""
    op.drop_column('investments', 'start_date')
