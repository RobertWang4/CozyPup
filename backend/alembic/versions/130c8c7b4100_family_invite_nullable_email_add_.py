"""family invite: nullable email, add expires_at

Revision ID: 130c8c7b4100
Revises: 20260412_04_flags_revoke
Create Date: 2026-04-14 02:53:05.535285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '130c8c7b4100'
down_revision: Union[str, Sequence[str], None] = '20260412_04_flags_revoke'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('family_invites', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('family_invites', 'invitee_email',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('family_invites', 'invitee_email',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.drop_column('family_invites', 'expires_at')
