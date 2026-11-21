"""Add bingo_boards.reset_count (방장이 빙고판을 다시 돌린 횟수, 1회까지 허용).

Revision ID: 5b7e1d3f9a62
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "5b7e1d3f9a62"
down_revision: Union[str, None] = "2d6f9c4a8b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bingo_boards",
        sa.Column("reset_count", mysql.TINYINT(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bingo_boards", "reset_count")
