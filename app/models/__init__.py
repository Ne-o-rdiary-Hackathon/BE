from app.db.base import Base
from app.models.user import User  # noqa: F401
from app.models.room import Room, RoomMember  # noqa: F401
from app.models.activity import Activity, ActivityCategory, UserResponse, UserResponseActivity  # noqa: F401
from app.models.bingo import BingoBoard, BingoCell, Verification  # noqa: F401

# 모델 모듈을 이 패키지에서 import해 Alembic이 테이블 메타데이터를 찾게 합니다.
