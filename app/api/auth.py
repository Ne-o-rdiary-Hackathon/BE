from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.common import BusinessException, ErrorCode, fail
from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_COOKIE,
    OAUTH_STATE_COOKIE,
    OAUTH_STATE_COOKIE_PATH,
    create_access_token,
    create_oauth_state,
    verify_oauth_state,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthUserResponse
from app.services.kakao_auth import KakaoAuthService

router = APIRouter(prefix="/api/auth", tags=["인증"])


def _failure_response(error: ErrorCode, message: str | None = None) -> JSONResponse:
    response = JSONResponse(
        status_code=error.status,
        content=fail(error.name, message or error.message),
        headers={"Cache-Control": "no-store"},
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path=OAUTH_STATE_COOKIE_PATH)
    return response


@router.get(
    "/kakao/login",
    summary="카카오 로그인 시작",
    description=(
        "브라우저를 카카오 인증 페이지로 리다이렉트합니다. "
        "state는 HttpOnly 쿠키에 저장되며 콜백에서 검증됩니다."
    ),
    status_code=302,
    responses={302: {"description": "카카오 인증 페이지로 리다이렉트"}},
)
async def kakao_login() -> Response:
    state = create_oauth_state()
    authorization_url = KakaoAuthService().create_authorization_url(state)
    response = RedirectResponse(authorization_url, status_code=302)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path=OAUTH_STATE_COOKIE_PATH,
    )
    return response


@router.get(
    "/kakao/callback",
    summary="카카오 로그인 콜백",
    description=(
        "카카오 인가 코드를 교환해 사용자를 생성하거나 로그인합니다. "
        "서비스 JWT는 HttpOnly 쿠키로 설정하고 프론트엔드로 리다이렉트합니다."
    ),
    status_code=303,
    responses={
        303: {"description": "로그인 성공, 프론트엔드로 리다이렉트"},
        400: {"description": "state, 인가 코드 오류 또는 사용자 취소"},
        502: {"description": "카카오 API 오류"},
        504: {"description": "카카오 API 타임아웃"},
    },
)
async def kakao_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not verify_oauth_state(expected_state, state):
        return _failure_response(ErrorCode.OAUTH_STATE_INVALID)

    if error:
        oauth_error = (
            ErrorCode.OAUTH_USER_CANCELLED
            if error == "access_denied"
            else ErrorCode.OAUTH_AUTHORIZATION_FAILED
        )
        return _failure_response(oauth_error)
    if not code:
        return _failure_response(ErrorCode.OAUTH_CODE_INVALID)

    try:
        user = await KakaoAuthService(db).authenticate(code)
        access_token = create_access_token(user.user_id)
    except BusinessException as exc:
        return _failure_response(exc.code, exc.message)

    response = RedirectResponse(settings.frontend_auth_success_url, status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(OAUTH_STATE_COOKIE, path=OAUTH_STATE_COOKIE_PATH)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="none" if settings.auth_cookie_secure else "lax",
        path="/",
    )
    return response


@router.get(
    "/me",
    response_model=AuthUserResponse,
    summary="현재 로그인 사용자 조회",
    description="서비스 JWT 쿠키 또는 Bearer 토큰으로 인증합니다.",
    responses={401: {"description": "JWT가 없거나 만료 또는 유효하지 않음"}},
)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user
