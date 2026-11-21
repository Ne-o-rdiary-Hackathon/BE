from fastapi import APIRouter
from sqlalchemy import text

from app.common import ok
from app.db.session import engine
from app.schemas.common import ApiResponse, BASE_ERROR_RESPONSES

router = APIRouter(tags=["상태 확인"])


@router.get(
    "/api/health",
    response_model=ApiResponse[dict[str, str]],
    summary="서버와 DB가 살아 있는지 확인",
    responses=BASE_ERROR_RESPONSES,
)
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "UP"
    except Exception:
        db = "DOWN"
    return ok({"server": "UP", "db": db})
