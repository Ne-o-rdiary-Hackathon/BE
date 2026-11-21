"""실행: uvicorn app.main:app --reload --port 8080
API 문서(자동 생성): http://localhost:8080/docs
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common import BusinessException, ErrorCode, fail
from app.core.config import settings
from app.api import auth, bingo, health

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
    if e.status_code == 404:
        return JSONResponse(status_code=404, content=fail(ErrorCode.NOT_FOUND.name, ErrorCode.NOT_FOUND.message))
    if e.status_code == 405:
        return JSONResponse(status_code=405, content=fail(ErrorCode.METHOD_NOT_ALLOWED.name,
                                                          ErrorCode.METHOD_NOT_ALLOWED.message))
    return JSONResponse(status_code=e.status_code, content=fail(f"HTTP_{e.status_code}", str(e.detail)))


@app.exception_handler(Exception)
async def handle_unknown(request: Request, e: Exception):
    log.exception("Unhandled exception")
    return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR.name, ErrorCode.INTERNAL_ERROR.message))


# ───────────────────────── 라우터 ─────────────────────────
# 새 라우터를 만들면 여기에 추가: app.include_router(user.router)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(bingo.router)

# S3를 설정하지 않은 개발 환경에서는 인증 사진을 로컬 폴더에서 제공합니다.
if not settings.s3_bucket:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
