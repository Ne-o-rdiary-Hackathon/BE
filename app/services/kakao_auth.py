from collections.abc import Callable
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import BusinessException, ErrorCode
from app.core.config import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import KakaoUserInfo

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"
HTTP_TIMEOUT_SECONDS = 10.0


class KakaoAuthService:
    def __init__(
        self,
        db: Session | None = None,
        http_client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ):
        self.db = db
        self.http_client_factory = http_client_factory

    def create_authorization_url(self, state: str) -> str:
        rest_api_key = settings.kakao_rest_api_key.get_secret_value()
        if not rest_api_key:
            raise BusinessException(ErrorCode.AUTH_CONFIGURATION_ERROR)

        query = urlencode({
            "client_id": rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "response_type": "code",
            "state": state,
        })
        return f"{AUTHORIZE_URL}?{query}"

    async def authenticate(self, code: str) -> User:
        self._validate_configuration()
        access_token = await self._request_access_token(code)
        kakao_user = await self._request_user_info(access_token)
        return self._find_or_create_user(kakao_user)

    @staticmethod
    def _validate_configuration() -> None:
        if not settings.kakao_rest_api_key.get_secret_value():
            raise BusinessException(ErrorCode.AUTH_CONFIGURATION_ERROR)
        if not settings.kakao_client_secret.get_secret_value():
            raise BusinessException(ErrorCode.AUTH_CONFIGURATION_ERROR)
        if len(settings.jwt_secret_key.get_secret_value().encode("utf-8")) < 32:
            raise BusinessException(ErrorCode.AUTH_CONFIGURATION_ERROR)

    async def _request_access_token(self, code: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.kakao_rest_api_key.get_secret_value(),
            "redirect_uri": settings.kakao_redirect_uri,
            "code": code,
            "client_secret": settings.kakao_client_secret.get_secret_value(),
        }
        try:
            async with self.http_client_factory(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(TOKEN_URL, data=data)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_TIMEOUT) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                raise BusinessException(ErrorCode.OAUTH_CODE_INVALID) from exc
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR) from exc

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR)
        return access_token

    async def _request_user_info(self, access_token: str) -> KakaoUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with self.http_client_factory(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(USER_INFO_URL, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_TIMEOUT) from exc
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR) from exc

        if not isinstance(payload, dict):
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR)

        kakao_id = payload.get("id")
        try:
            if isinstance(kakao_id, bool) or not isinstance(kakao_id, (int, str)):
                raise ValueError
            if isinstance(kakao_id, str) and not kakao_id.isdecimal():
                raise ValueError
            normalized_kakao_id = int(kakao_id)
        except (TypeError, ValueError):
            raise BusinessException(ErrorCode.OAUTH_PROVIDER_ERROR) from None

        account = payload.get("kakao_account")
        account = account if isinstance(account, dict) else {}
        profile = account.get("profile")
        profile = profile if isinstance(profile, dict) else {}
        properties = payload.get("properties")
        properties = properties if isinstance(properties, dict) else {}

        nickname = profile.get("nickname") or properties.get("nickname")
        profile_image_url = profile.get("profile_image_url") or properties.get("profile_image")
        return KakaoUserInfo(
            kakao_id=normalized_kakao_id,
            nickname=nickname.strip()[:30] if isinstance(nickname, str) and nickname.strip() else None,
            profile_image_url=(
                profile_image_url
                if isinstance(profile_image_url, str) and len(profile_image_url) <= 1000
                else None
            ),
        )

    def _find_or_create_user(self, kakao_user: KakaoUserInfo) -> User:
        if self.db is None:
            raise BusinessException(ErrorCode.INTERNAL_ERROR)

        repository = UserRepository(self.db)
        nickname = kakao_user.nickname or f"사용자_{kakao_user.kakao_id}"
        try:
            with self.db.begin():
                user = repository.get_by_kakao_id(kakao_user.kakao_id)
                if user is None:
                    return repository.create(
                        kakao_id=kakao_user.kakao_id,
                        nickname=nickname,
                        profile_image_url=kakao_user.profile_image_url,
                    )
                return repository.update_profile(
                    user=user,
                    nickname=kakao_user.nickname,
                    profile_image_url=kakao_user.profile_image_url,
                )
        except IntegrityError as exc:
            self.db.rollback()
            existing_user = repository.get_by_kakao_id(kakao_user.kakao_id)
            if existing_user is not None:
                return existing_user
            raise BusinessException(ErrorCode.INTERNAL_ERROR, "회원 정보를 저장하지 못했습니다.") from exc
