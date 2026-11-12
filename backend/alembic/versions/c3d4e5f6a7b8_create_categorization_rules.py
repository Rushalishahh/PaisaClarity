"""create categorization rules table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'categorization_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.String(length=200), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('category_name', sa.String(length=100), nullable=False),
        sa.Column('match_type', sa.String(length=50), nullable=False, server_default='contains'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categorization_rules_id'), 'categorization_rules', ['id'], unique=False)
    op.create_index(op.f('ix_categorization_rules_user_id'), 'categorization_rules', ['user_id'], unique=False)
    op.create_index(op.f('ix_categorization_rules_category_id'), 'categorization_rules', ['category_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_categorization_rules_category_id'), table_name='categorization_rules')
    op.drop_index(op.f('ix_categorization_rules_user_id'), table_name='categorization_rules')
    op.drop_index(op.f('ix_categorization_rules_id'), table_name='categorization_rules')
    op.drop_table('categorization_rules')
