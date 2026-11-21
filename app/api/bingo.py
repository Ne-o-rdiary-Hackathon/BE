from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.common import BusinessException, ErrorCode, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.bingo import (
    ApiResponse,
    BingoBoardResponse,
    BingoResultResponse,
    VerificationResponse,
)
from app.services.bingo_service import BingoService
from app.services.image_storage import MAX_IMAGE_BYTES, get_image_storage

router = APIRouter(prefix="/api/rooms/{room_id}", tags=["빙고"])


def get_bingo_service(db: Session = Depends(get_db)) -> BingoService:
    return BingoService(db, get_image_storage())


@router.post(
    "/bingo-board",
    summary="BINGO-01 빙고판 생성 (방장)",
    description=(
        "멤버들이 제출한 설문으로 활동 9개를 골라 빙고판을 만들고 방을 IN_PROGRESS로 바꿉니다. "
        "점수 1위 활동은 가운데(position 4)에 놓입니다."
    ),
    response_model=ApiResponse[BingoBoardResponse],
)
def create_bingo_board(
    room_id: int,
    user: User = Depends(get_current_user),
    service: BingoService = Depends(get_bingo_service),
):
    return ok(service.create_board(room_id, user))


@router.get(
    "/bingo-board",
    summary="BINGO-02 빙고판·진행 현황 조회",
    response_model=ApiResponse[BingoBoardResponse],
)
def get_bingo_board(
    room_id: int,
    user: User = Depends(get_current_user),
    service: BingoService = Depends(get_bingo_service),
):
    return ok(service.get_board(room_id, user))


@router.post(
    "/bingo-board/reset",
    summary="BINGO-03 빙고판 다시 돌리기 (방장, 1회)",
    description=(
        "인증된 칸이 하나도 없을 때만 방장이 한 번 다시 뽑을 수 있습니다. "
        "지금 빙고판에 있던 활동은 최대한 빼고 새로 고릅니다."
    ),
    response_model=ApiResponse[BingoBoardResponse],
)
def reset_bingo_board(
    room_id: int,
    user: User = Depends(get_current_user),
    service: BingoService = Depends(get_bingo_service),
):
    return ok(service.reset_board(room_id, user))


@router.post(
    "/bingo-board/cells/{cell_id}/verification",
    summary="VERIFY-01 사진 인증 (+빙고 판정)",
    description="multipart/form-data의 image 필드로 jpg·png·webp 사진(10MB 이하)을 올립니다.",
    response_model=ApiResponse[VerificationResponse],
)
def verify_bingo_cell(
    room_id: int,
    cell_id: int,
    image: UploadFile = File(..., description="인증 사진 (jpg·png·webp, 10MB 이하)"),
    user: User = Depends(get_current_user),
    service: BingoService = Depends(get_bingo_service),
):
    data = image.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise BusinessException(ErrorCode.IMAGE_TOO_LARGE)
    return ok(service.verify_cell(room_id, cell_id, user, data))


@router.get(
    "/result",
    summary="RESULT-01 빙고 결과 조회",
    response_model=ApiResponse[BingoResultResponse],
)
def get_bingo_result(
    room_id: int,
    user: User = Depends(get_current_user),
    service: BingoService = Depends(get_bingo_service),
):
    return ok(service.get_result(room_id, user))
