from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_kakao_id(self, kakao_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.kakao_id == kakao_id))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def create(self, kakao_id: int, nickname: str, profile_image_url: str | None) -> User:
        user = User(
            kakao_id=kakao_id,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )
        self.db.add(user)
        self.db.flush()
        return user

    @staticmethod
    def update_profile(
        user: User,
        nickname: str | None,
        profile_image_url: str | None,
    ) -> User:
        if nickname:
            user.nickname = nickname
        if profile_image_url:
            user.profile_image_url = profile_image_url
        return user
