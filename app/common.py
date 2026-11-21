"""공통 응답 형식과 에러 코드

성공: { "success": true, "data": {...}, "error": null }
실패: { "success": false, "data": null, "error": { "code": "...", "message": "..." } }

라우터에서는 return ok(data), 에러는 raise BusinessException(ErrorCode.XXX)
"""
from enum import Enum
from typing import Any


class ErrorCode(Enum):
    """에러 코드 모음. 기능을 만들 때 여기에 추가하세요. (메시지는 서로 달라야 합니다)
    예: ROOM_NOT_FOUND = (404, "방을 찾을 수 없습니다.")"""
    INVALID_INPUT = (400, "입력값이 올바르지 않습니다.")
    UNAUTHORIZED = (401, "로그인이 필요합니다.")
    FORBIDDEN = (403, "권한이 없습니다.")
    NOT_FOUND = (404, "요청한 경로를 찾을 수 없습니다.")
    METHOD_NOT_ALLOWED = (405, "지원하지 않는 요청 방식입니다.")
    OAUTH_STATE_INVALID = (400, "로그인 요청이 만료되었거나 올바르지 않습니다.")
    OAUTH_USER_CANCELLED = (400, "카카오 로그인이 취소되었습니다.")
    OAUTH_AUTHORIZATION_FAILED = (400, "카카오 인증을 완료하지 못했습니다.")
    OAUTH_CODE_INVALID = (400, "카카오 인증 코드가 유효하지 않습니다.")
    OAUTH_PROVIDER_ERROR = (502, "카카오 인증 서비스와 통신하지 못했습니다.")
    OAUTH_PROVIDER_TIMEOUT = (504, "카카오 인증 서비스 응답 시간이 초과되었습니다.")
    AUTH_CONFIGURATION_ERROR = (500, "로그인 서버 설정이 올바르지 않습니다.")
    INVALID_ACCESS_TOKEN = (401, "로그인 정보가 유효하지 않거나 만료되었습니다.")
    INTERNAL_ERROR = (500, "서버 오류가 발생했습니다.")

    @property
    def status(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class BusinessException(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None):
        self.code = code
        self.message = message or code.message
        super().__init__(self.message)


def ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


def fail(code: str, message: str) -> dict:
    return {"success": False, "data": None, "error": {"code": code, "message": message}}
