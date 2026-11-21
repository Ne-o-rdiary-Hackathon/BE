import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from app.api import dependencies
from app.common import BusinessException, ErrorCode
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, verify_oauth_state
from app.main import app
from app.services import kakao_auth


class FakeSession:
    def begin(self):
        return nullcontext()

    def rollback(self) -> None:
        pass


class FakeUserRepository:
    def __init__(self, user=None):
        self.user = user
        self.created = None
        self.updated = None

    def get_by_kakao_id(self, kakao_id: int):
        return self.user if self.user and self.user.kakao_id == kakao_id else None

    def create(self, kakao_id: int, nickname: str, profile_image_url: str | None):
        self.created = (kakao_id, nickname, profile_image_url)
        self.user = SimpleNamespace(
            user_id=7,
            kakao_id=kakao_id,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )
        return self.user

    def update_profile(self, user, nickname: str | None, profile_image_url: str | None):
        self.updated = (nickname, profile_image_url)
        return user


def configure_kakao_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kakao_rest_api_key", SecretStr("test-rest-key"))
    monkeypatch.setattr(settings, "kakao_client_secret", SecretStr("test-client-secret"))
    monkeypatch.setattr(settings, "jwt_secret_key", SecretStr("test-jwt-secret-at-least-32-characters"))


def make_client_factory(handler):
    def factory(*, timeout):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return factory


def api_get(path: str, headers: dict[str, str] | None = None, follow_redirects: bool = True):
    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=follow_redirects,
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def token_response(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/oauth/token":
        return httpx.Response(200, json={"access_token": "kakao-access-token"})
    return httpx.Response(
        200,
        json={
            "id": 1234,
            "kakao_account": {
                "profile": {
                    "nickname": "빙고 유저",
                    "profile_image_url": "https://example.com/profile.png",
                }
            },
        },
    )


def test_new_kakao_user_is_created_with_profile_fallback(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    repository = FakeUserRepository()
    monkeypatch.setattr(kakao_auth, "UserRepository", lambda db: repository)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "kakao-access-token"})
        return httpx.Response(200, json={"id": 1234, "kakao_account": {}})

    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(handler))
    user = asyncio.run(service.authenticate("authorization-code"))

    assert user.user_id == 7
    assert repository.created == (1234, "사용자_1234", None)


def test_existing_kakao_user_is_logged_in_and_profile_updated(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    existing_user = SimpleNamespace(
        user_id=3,
        kakao_id=1234,
        nickname="이전 닉네임",
        profile_image_url=None,
    )
    repository = FakeUserRepository(existing_user)
    monkeypatch.setattr(kakao_auth, "UserRepository", lambda db: repository)
    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(token_response))

    user = asyncio.run(service.authenticate("authorization-code"))

    assert user is existing_user
    assert repository.created is None
    assert repository.updated == ("빙고 유저", "https://example.com/profile.png")


def test_invalid_authorization_code_returns_bad_request(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(handler))

    with pytest.raises(BusinessException) as exc_info:
        asyncio.run(service.authenticate("invalid-code"))

    assert exc_info.value.code is ErrorCode.OAUTH_CODE_INVALID
    assert exc_info.value.code.status == 400


def test_oauth_state_must_match() -> None:
    assert verify_oauth_state("expected", "expected")
    assert not verify_oauth_state("expected", "different")
    assert not verify_oauth_state(None, "expected")


def test_service_jwt_round_trip_and_invalid_token(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    token = create_access_token(42)

    assert decode_access_token(token)["sub"] == "42"
    with pytest.raises(BusinessException) as exc_info:
        decode_access_token("not-a-jwt")
    assert exc_info.value.code is ErrorCode.INVALID_ACCESS_TOKEN


def test_current_user_endpoint_accepts_service_jwt_cookie(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    user = SimpleNamespace(user_id=42, nickname="빙고 유저", profile_image_url=None)
    monkeypatch.setattr(
        dependencies.UserRepository,
        "get_by_id",
        lambda self, user_id: user if user_id == 42 else None,
    )
    token = create_access_token(user.user_id)

    response = api_get("/api/auth/me", headers={"Cookie": f"access_token={token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": 42,
        "nickname": "빙고 유저",
        "profile_image_url": None,
    }


def test_missing_kakao_user_id_is_rejected(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "kakao-access-token"})
        return httpx.Response(200, json={"kakao_account": {}})

    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(handler))

    with pytest.raises(BusinessException) as exc_info:
        asyncio.run(service.authenticate("authorization-code"))

    assert exc_info.value.code is ErrorCode.OAUTH_PROVIDER_ERROR


def test_kakao_timeout_returns_gateway_timeout(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out", request=request)

    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(handler))

    with pytest.raises(BusinessException) as exc_info:
        asyncio.run(service.authenticate("authorization-code"))

    assert exc_info.value.code is ErrorCode.OAUTH_PROVIDER_TIMEOUT
    assert exc_info.value.code.status == 504


def test_kakao_user_info_error_returns_bad_gateway(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "kakao-access-token"})
        return httpx.Response(500, json={"error": "internal_error"})

    service = kakao_auth.KakaoAuthService(FakeSession(), make_client_factory(handler))

    with pytest.raises(BusinessException) as exc_info:
        asyncio.run(service.authenticate("authorization-code"))

    assert exc_info.value.code is ErrorCode.OAUTH_PROVIDER_ERROR
    assert exc_info.value.code.status == 502


def test_callback_rejects_missing_state_cookie() -> None:
    response = api_get("/api/auth/kakao/callback?code=authorization-code&state=state-value")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.OAUTH_STATE_INVALID.name


def test_kakao_login_redirects_with_state_cookie(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kakao_rest_api_key", SecretStr("test-rest-key"))
    monkeypatch.setattr(settings, "kakao_redirect_uri", "http://localhost:8080/api/auth/kakao/callback")

    response = api_get("/api/auth/kakao/login", follow_redirects=False)
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)

    assert response.status_code == 302
    assert location.netloc == "kauth.kakao.com"
    assert query["client_id"] == ["test-rest-key"]
    assert query["redirect_uri"] == ["http://localhost:8080/api/auth/kakao/callback"]
    assert query["response_type"] == ["code"]
    assert "state" in query
    assert "HttpOnly" in response.headers["set-cookie"]


def test_callback_reports_user_cancellation_and_consumes_state() -> None:
    response = api_get(
        "/api/auth/kakao/callback?error=access_denied&state=state-value",
        headers={"Cookie": "kakao_oauth_state=state-value"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.OAUTH_USER_CANCELLED.name
    assert "kakao_oauth_state" in response.headers["set-cookie"]


def test_callback_clears_state_and_sets_http_only_service_cookie(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    monkeypatch.setattr(settings, "frontend_auth_success_url", "http://localhost:3000/auth/callback")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    authenticate = AsyncMock(return_value=SimpleNamespace(user_id=7))
    monkeypatch.setattr(kakao_auth.KakaoAuthService, "authenticate", authenticate)

    response = api_get(
        "/api/auth/kakao/callback?code=authorization-code&state=state-value",
        headers={"Cookie": "kakao_oauth_state=state-value"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/auth/callback"
    assert "access_token=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "kakao_oauth_state" in response.headers["set-cookie"]
    assert "access_token" not in response.headers["location"]


def test_callback_uses_cross_site_cookie_settings_when_secure(monkeypatch) -> None:
    configure_kakao_settings(monkeypatch)
    monkeypatch.setattr(settings, "frontend_auth_success_url", "https://frontend.example/auth/callback")
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    authenticate = AsyncMock(return_value=SimpleNamespace(user_id=7))
    monkeypatch.setattr(kakao_auth.KakaoAuthService, "authenticate", authenticate)

    response = api_get(
        "/api/auth/kakao/callback?code=authorization-code&state=state-value",
        headers={"Cookie": "kakao_oauth_state=state-value"},
        follow_redirects=False,
    )

    set_cookie = response.headers["set-cookie"]
    assert response.status_code == 303
    assert "SameSite=none" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
