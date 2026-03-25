"""add context_summary to chat_sessions

Revision ID: 6459dce44bea
Revises: 93096dfcaafa
Create Date: 2026-03-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6459dce44bea'
down_revision: Union[str, Sequence[str], None] = '93096dfcaafa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_sessions', sa.Column('context_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('chat_sessions', sa.Column('summarized_up_to', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_sessions', 'summarized_up_to')
    op.drop_column('chat_sessions', 'context_summary')
