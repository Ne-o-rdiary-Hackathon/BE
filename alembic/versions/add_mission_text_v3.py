"""Add bingo_cells.mission_text (AI가 만든 빙고 칸 미션 문구).

Revision ID: 7c3a9e2f4b18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7c3a9e2f4b18"
down_revision: Union[str, None] = "2d6f9c4a8b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bingo_cells", sa.Column("mission_text", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("bingo_cells", "mission_text")
