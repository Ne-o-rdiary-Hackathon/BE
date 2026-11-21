from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, now_kst
from app.db.types import BigId


class ActivityCategory(Base):
    __tablename__ = "activity_categories"

    category_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("activity_categories.category_id"), index=True
    )
    category_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=now_kst)


class Activity(Base):
    __tablename__ = "activities"

    activity_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("activity_categories.category_id"), nullable=False
    )
    activity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=now_kst)


class ResponseStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"


class SelectionType:
    DESIRED = "DESIRED"
    BORED = "BORED"


class UserResponse(Base):
    """방 멤버가 제출한 '하고 싶은 활동 / 질린 활동' 설문."""

    __tablename__ = "user_responses"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_user_responses_room_user"),
        ForeignKeyConstraint(
            ["room_id", "user_id"],
            ["room_members.room_id", "room_members.user_id"],
            name="fk_user_responses_room_member",
        ),
    )

    response_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(BigId, nullable=False)
    user_id: Mapped[int] = mapped_column(BigId, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=ResponseStatus.DRAFT, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=now_kst)


class UserResponseActivity(Base):
    __tablename__ = "user_response_activities"
    __table_args__ = (
        UniqueConstraint("response_id", "activity_id", name="uq_response_activities_response_activity"),
    )

    response_activity_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("user_responses.response_id"), nullable=False
    )
    activity_id: Mapped[int] = mapped_column(BigId, ForeignKey("activities.activity_id"), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)
