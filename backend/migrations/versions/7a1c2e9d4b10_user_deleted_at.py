"""users.deleted_at (회원 탈퇴)

Revision ID: 7a1c2e9d4b10
Revises: 4e5efe56a864
Create Date: 2026-10-27 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c2e9d4b10"
down_revision: Union[str, None] = "4e5efe56a864"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
