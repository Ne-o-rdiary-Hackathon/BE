from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    """공통 응답 형식 (Swagger 문서용)."""

    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None


class BingoCellResponse(BaseModel):
    cell_id: int
    position: int
    activity_name: str
    score: int
    status: str
    image_url: str | None


class BoardMemberResponse(BaseModel):
    user_id: int
    nickname: str
    profile_image_url: str | None
    role: str


class BingoBoardResponse(BaseModel):
    """BINGO-01, BINGO-02, BINGO-03"""

    room_name: str
    is_owner: bool
    reset_remaining: int
    members: list[BoardMemberResponse]
    room_status: str
    target_bingo: int
    achieved_bingo: int
    completed_cells: int
    bingo_cell_ids: list[int]
    cells: list[BingoCellResponse]


class VerificationResponse(BaseModel):
    """VERIFY-01"""

    cell: BingoCellResponse
    achieved_bingo: int
    completed_cells: int
    new_bingo_cell_ids: list[int]
    bingo_cell_ids: list[int]
    room_completed: bool


class ResultMemberResponse(BaseModel):
    nickname: str
    profile_image_url: str | None
    verified_count: int


class BingoResultResponse(BaseModel):
    """RESULT-01"""

    room_name: str
    target_bingo: int
    achieved_bingo: int
    completed_cells: int
    bingo_cell_ids: list[int]
    members: list[ResultMemberResponse]
    cells: list[BingoCellResponse]
