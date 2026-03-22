"""add photos to calendar_events

Revision ID: 31de7f1a2e4e
Revises: dd97e66df9e4
Create Date: 2026-03-22 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31de7f1a2e4e'
down_revision: Union[str, Sequence[str], None] = 'dd97e66df9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('calendar_events', sa.Column('photos', sa.JSON(), server_default='[]', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('calendar_events', 'photos')
