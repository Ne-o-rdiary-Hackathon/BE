"""Create the group bingo schema.

Revision ID: 8f21c0a3d7b4
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "8f21c0a3d7b4"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = {
    "users",
    "auth_sessions",
    "rooms",
    "room_members",
    "activity_categories",
    "activities",
    "user_responses",
    "user_response_activities",
    "bingo_boards",
    "bingo_cells",
    "verifications",
}


def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kakao_id", sa.String(length=100), nullable=False),
        sa.Column("nickname", sa.String(length=30), nullable=False),
        sa.Column("profile_image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("kakao_id", name="uq_users_kakao_id"),
    )


def _upgrade_existing_users() -> None:
    connection = op.get_bind()
    long_profile_urls = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM users "
            "WHERE profile_image_url IS NOT NULL AND CHAR_LENGTH(profile_image_url) > 500"
        )
    ).scalar_one()
    if long_profile_urls:
        raise RuntimeError(
            "Cannot reduce users.profile_image_url to VARCHAR(500): "
            "existing rows contain longer URLs."
        )

    op.alter_column(
        "users",
        "kakao_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(length=100),
        existing_nullable=False,
        nullable=False,
    )
    op.alter_column(
        "users",
        "profile_image_url",
        existing_type=sa.String(length=1000),
        type_=sa.String(length=500),
        existing_nullable=True,
        nullable=True,
    )
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=True,
        server_default=None,
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _create_users()
    else:
        existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
        conflicts = existing_tables.intersection(TABLES - {"users"})
        if conflicts:
            names = ", ".join(sorted(conflicts))
            raise RuntimeError(
                f"Cannot apply the full schema because these tables already exist: {names}"
            )
        if "users" in existing_tables:
            _upgrade_existing_users()
        else:
            _create_users()

    op.create_table(
        "auth_sessions",
        sa.Column("session_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_auth_sessions_user_id"),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "rooms",
        sa.Column("room_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("room_name", sa.String(length=20), nullable=False),
        sa.Column("invite_code", sa.String(length=32), nullable=False),
        sa.Column("max_members", mysql.TINYINT(), nullable=False),
        sa.Column("target_bingo", mysql.TINYINT(), server_default=sa.text("3"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'RECRUITING'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("CHAR_LENGTH(room_name) BETWEEN 2 AND 20", name="ck_rooms_room_name_length"),
        sa.CheckConstraint("max_members BETWEEN 2 AND 9", name="ck_rooms_max_members"),
        sa.CheckConstraint("target_bingo IN (1, 2, 3, 8)", name="ck_rooms_target_bingo"),
        sa.CheckConstraint(
            "status IN ('RECRUITING', 'IN_PROGRESS', 'COMPLETED')",
            name="ck_rooms_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], name="fk_rooms_owner_id"),
        sa.PrimaryKeyConstraint("room_id"),
        sa.UniqueConstraint("invite_code", name="uq_rooms_invite_code"),
    )
    op.create_index("ix_rooms_owner_id", "rooms", ["owner_id"])
    op.create_index("ix_rooms_status", "rooms", ["status"])
    op.create_index("ix_rooms_created_at", "rooms", ["created_at"])

    op.create_table(
        "room_members",
        sa.Column("room_member_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default=sa.text("'MEMBER'"), nullable=False),
        sa.Column("joined_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("role IN ('OWNER', 'MEMBER')", name="ck_room_members_role"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name="fk_room_members_room_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_room_members_user_id"),
        sa.PrimaryKeyConstraint("room_member_id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),
    )
    op.create_index("ix_room_members_user_id", "room_members", ["user_id"])

    op.create_table(
        "activity_categories",
        sa.Column("category_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("category_name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["activity_categories.category_id"],
            name="fk_activity_categories_parent_id",
        ),
        sa.PrimaryKeyConstraint("category_id"),
    )
    op.create_index("ix_activity_categories_parent_id", "activity_categories", ["parent_id"])

    op.create_table(
        "activities",
        sa.Column("activity_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["activity_categories.category_id"],
            name="fk_activities_category_id",
        ),
        sa.PrimaryKeyConstraint("activity_id"),
    )

    op.create_table(
        "user_responses",
        sa.Column("response_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'SUBMITTED')", name="ck_user_responses_status"),
        sa.ForeignKeyConstraint(
            ["room_id", "user_id"],
            ["room_members.room_id", "room_members.user_id"],
            name="fk_user_responses_room_member",
        ),
        sa.PrimaryKeyConstraint("response_id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_user_responses_room_user"),
    )

    op.create_table(
        "user_response_activities",
        sa.Column("response_activity_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("response_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("selection_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "selection_type IN ('DESIRED', 'BORED')",
            name="ck_response_activities_selection_type",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.activity_id"],
            name="fk_response_activities_activity_id",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["user_responses.response_id"],
            name="fk_response_activities_response_id",
        ),
        sa.PrimaryKeyConstraint("response_activity_id"),
        sa.UniqueConstraint(
            "response_id",
            "activity_id",
            name="uq_response_activities_response_activity",
        ),
    )
    op.create_index(
        "ix_response_activities_activity_selection",
        "user_response_activities",
        ["activity_id", "selection_type"],
    )

    op.create_table(
        "bingo_boards",
        sa.Column("board_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("board_size", mysql.TINYINT(), server_default=sa.text("3"), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("board_size = 3", name="ck_bingo_boards_board_size"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name="fk_bingo_boards_room_id"),
        sa.PrimaryKeyConstraint("board_id"),
        sa.UniqueConstraint("room_id", name="uq_bingo_boards_room_id"),
    )

    op.create_table(
        "bingo_cells",
        sa.Column("cell_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("board_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("position", mysql.TINYINT(), nullable=False),
        sa.Column("match_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("position BETWEEN 0 AND 8", name="ck_bingo_cells_position"),
        sa.CheckConstraint("match_rate BETWEEN 0 AND 100", name="ck_bingo_cells_match_rate"),
        sa.CheckConstraint("status IN ('PENDING', 'COMPLETED')", name="ck_bingo_cells_status"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.activity_id"], name="fk_bingo_cells_activity_id"),
        sa.ForeignKeyConstraint(["board_id"], ["bingo_boards.board_id"], name="fk_bingo_cells_board_id"),
        sa.PrimaryKeyConstraint("cell_id"),
        sa.UniqueConstraint("board_id", "activity_id", name="uq_bingo_cells_board_activity"),
        sa.UniqueConstraint("board_id", "position", name="uq_bingo_cells_board_position"),
    )

    op.create_table(
        "verifications",
        sa.Column("verification_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cell_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("image_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["cell_id"], ["bingo_cells.cell_id"], name="fk_verifications_cell_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_verifications_user_id"),
        sa.PrimaryKeyConstraint("verification_id"),
        sa.UniqueConstraint("cell_id", name="uq_verifications_cell_id"),
    )
    op.create_index("ix_verifications_user_id", "verifications", ["user_id"])


def downgrade() -> None:
    raise RuntimeError(
        "This consolidated baseline may include pre-existing user data. "
        "Restore a verified backup before removing its tables."
    )
