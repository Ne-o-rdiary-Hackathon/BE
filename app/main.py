"""실행: uvicorn app.main:app --reload --port 8080
API 문서(자동 생성): http://localhost:8080/docs
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import activities, auth, health, home
from app.common import BusinessException, ErrorCode, fail
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backend")


app = FastAPI(title="Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ───────────────────────── 예외 → 공통 응답 형식 ─────────────────────────

@app.exception_handler(BusinessException)
async def handle_business(request: Request, e: BusinessException):
    return JSONResponse(status_code=e.code.status, content=fail(e.code.name, e.message))


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, e: RequestValidationError):
    errors = e.errors()
    message = ErrorCode.INVALID_INPUT.message
    if errors:
        loc = [str(x) for x in errors[0].get("loc", []) if x not in ("body", "query", "path", "form")]
        message = f"{'.'.join(loc)}: {errors[0].get('msg')}" if loc else errors[0].get("msg")
    return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT.name, message))


@app.exception_handler(StarletteHTTPException)
async def handle_http(request: Request, e: StarletteHTTPException):
    known_errors = {
        400: ErrorCode.INVALID_INPUT,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
    }
    error = known_errors.get(e.status_code)
    if error is not None:
        return JSONResponse(
            status_code=error.status,
            content=fail(error.name, error.message),
        )
    if e.status_code >= 500:
        return JSONResponse(
            status_code=ErrorCode.INTERNAL_ERROR.status,
            content=fail(ErrorCode.INTERNAL_ERROR.name, ErrorCode.INTERNAL_ERROR.message),
        )
    return JSONResponse(status_code=e.status_code, content=fail(f"HTTP_{e.status_code}", str(e.detail)))


@app.exception_handler(Exception)
async def handle_unknown(request: Request, e: Exception):
    log.exception("Unhandled exception")
    return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR.name, ErrorCode.INTERNAL_ERROR.message))


# ───────────────────────── 라우터 ─────────────────────────
# 새 라우터를 만들면 여기에 추가: app.include_router(user.router)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(home.router)
app.include_router(home.bingo_router)
app.include_router(activities.router)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
                if settings.app_env != "development" or not settings.dev_auth_enabled:
                    operation["parameters"] = [
                        parameter
                        for parameter in operation.get("parameters", [])
                        if not (
                            parameter.get("in") == "header"
                            and parameter.get("name", "").lower() == "x-dev-user-id"
                        )
                    ]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
