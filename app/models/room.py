from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, now_kst
from app.db.types import BigId, TinyInt
from app.models.user import User


class RoomStatus:
    RECRUITING = "RECRUITING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class MemberRole:
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigId, ForeignKey("users.user_id"), nullable=False, index=True)
    room_name: Mapped[str] = mapped_column(String(20), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    max_members: Mapped[int] = mapped_column(TinyInt, nullable=False)
    target_bingo: Mapped[int] = mapped_column(TinyInt, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RoomStatus.RECRUITING, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=now_kst)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),)

    room_member_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(BigId, ForeignKey("rooms.room_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigId, ForeignKey("users.user_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default=MemberRole.MEMBER, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)

    user: Mapped[User] = relationship(lazy="joined")
