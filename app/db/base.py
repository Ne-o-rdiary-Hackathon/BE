from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

KST = ZoneInfo("Asia/Seoul")


class Base(DeclarativeBase):
    """모든 SQLAlchemy 모델의 부모 클래스."""


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None, microsecond=0)


class TimestampMixin:
    """생성/수정 시각 컬럼이 필요한 모델에 추가합니다."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, onupdate=now_kst, nullable=False)
