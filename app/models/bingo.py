from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, now_kst
from app.db.types import BigId, TinyInt
from app.models.activity import Activity


class CellStatus:
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class BingoBoard(Base):
    __tablename__ = "bingo_boards"

    board_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(BigId, ForeignKey("rooms.room_id"), unique=True, nullable=False)
    board_size: Mapped[int] = mapped_column(TinyInt, default=3, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)

    cells: Mapped[list["BingoCell"]] = relationship(
        back_populates="board", order_by="BingoCell.position", lazy="selectin"
    )


class BingoCell(Base):
    __tablename__ = "bingo_cells"
    __table_args__ = (
        UniqueConstraint("board_id", "activity_id", name="uq_bingo_cells_board_activity"),
        UniqueConstraint("board_id", "position", name="uq_bingo_cells_board_position"),
    )

    cell_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(BigId, ForeignKey("bingo_boards.board_id"), nullable=False)
    activity_id: Mapped[int] = mapped_column(BigId, ForeignKey("activities.activity_id"), nullable=False)
    position: Mapped[int] = mapped_column(TinyInt, nullable=False)
    match_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    mission_text: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=CellStatus.PENDING, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    board: Mapped[BingoBoard] = relationship(back_populates="cells")
    activity: Mapped[Activity] = relationship(lazy="joined")
    verification: Mapped["Verification | None"] = relationship(
        back_populates="cell", uselist=False, lazy="joined"
    )


class Verification(Base):
    __tablename__ = "verifications"

    verification_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    cell_id: Mapped[int] = mapped_column(BigId, ForeignKey("bingo_cells.cell_id"), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigId, ForeignKey("users.user_id"), nullable=False, index=True)
    image_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)

    cell: Mapped[BingoCell] = relationship(back_populates="verification")
