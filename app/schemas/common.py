from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool
    data: DataT | None
    error: ErrorDetail | None


BASE_ERROR_RESPONSES = {
    404: {"model": ApiResponse[None], "description": "요청한 리소스를 찾을 수 없습니다."},
    405: {"model": ApiResponse[None], "description": "지원하지 않는 요청 방식입니다."},
    500: {"model": ApiResponse[None], "description": "서버 오류가 발생했습니다."},
}

AUTH_ERROR_RESPONSES = {
    **BASE_ERROR_RESPONSES,
    401: {"model": ApiResponse[None], "description": "로그인이 필요합니다."},
}

PUBLIC_ERROR_RESPONSES = {
    **BASE_ERROR_RESPONSES,
    400: {"model": ApiResponse[None], "description": "요청 값이 올바르지 않습니다."},
}

AUTH_VALIDATION_ERROR_RESPONSES = {
    **AUTH_ERROR_RESPONSES,
    400: {"model": ApiResponse[None], "description": "요청 값이 올바르지 않습니다."},
}

JOIN_ERROR_RESPONSES = {
    **AUTH_VALIDATION_ERROR_RESPONSES,
    409: {"model": ApiResponse[None], "description": "현재 상태에서 요청을 처리할 수 없습니다."},
}
