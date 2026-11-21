from pydantic import BaseModel, ConfigDict


class KakaoUserInfo(BaseModel):
    kakao_id: int
    nickname: str | None = None
    profile_image_url: str | None = None


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    nickname: str
    profile_image_url: str | None
