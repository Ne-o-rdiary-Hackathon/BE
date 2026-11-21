from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class RoomCreateRequest(BaseModel):
    room_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=20),
    ]
    max_members: int = Field(ge=2, le=9)
    target_bingo: Literal[1, 2, 3, 8]


class RoomCreateResponse(BaseModel):
    room_id: int
    room_name: str
    max_members: int
    current_members: int
    target_bingo: int
    status: str
    invite_url: str


class InviteRoomInfo(BaseModel):
    room_id: int
    room_name: str
    status: str
    current_members: int
    max_members: int
    target_bingo: int
    achieved_bingo: int
    can_join: bool


class InviteValidationResponse(BaseModel):
    valid: bool
    room: InviteRoomInfo | None


class RoomJoinResponse(BaseModel):
    room_id: int
