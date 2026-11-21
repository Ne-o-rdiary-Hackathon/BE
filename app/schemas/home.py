from enum import Enum

from pydantic import BaseModel


class RoomStatusFilter(str, Enum):
    ALL = "ALL"
    RECRUITING = "RECRUITING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class RoomSummary(BaseModel):
    room_id: int
    room_name: str
    status: str
    current_members: int
    max_members: int
    target_bingo: int
    achieved_bingo: int
    completed_cells: int
    total_cells: int
    invite_url: str


class RoomListResponse(BaseModel):
    total_count: int
    page: int
    size: int
    rooms: list[RoomSummary]
