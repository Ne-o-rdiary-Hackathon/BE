from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.home_dependencies import get_current_user_id
from app.common import BusinessException, ErrorCode, ok
from app.core.invites import build_invite_url, generate_invite_code
from app.db.session import get_db
from app.schemas.common import (
    ApiResponse,
    AUTH_VALIDATION_ERROR_RESPONSES,
    JOIN_ERROR_RESPONSES,
    PUBLIC_ERROR_RESPONSES,
)
from app.schemas.home import RoomListResponse, RoomStatusFilter
from app.schemas.rooms import (
    InviteRoomInfo,
    InviteValidationResponse,
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinResponse,
)

router = APIRouter(tags=["홈"])
bingo_router = APIRouter(tags=["빙고"])

_BINGO_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def _get_achieved_bingo_counts(db: Session, room_ids: list[int]) -> dict[int, int]:
    completed_positions: dict[int, set[int]] = {
        room_id: set() for room_id in room_ids
    }
    if room_ids:
        positions_query = text(
            "SELECT boards.room_id, cells.position "
            "FROM bingo_boards AS boards "
            "JOIN bingo_cells AS cells ON cells.board_id = boards.board_id "
            "WHERE boards.room_id IN :room_ids AND cells.status = 'COMPLETED'"
        ).bindparams(bindparam("room_ids", expanding=True))
        for row in db.execute(positions_query, {"room_ids": room_ids}).mappings():
            completed_positions[row["room_id"]].add(row["position"])

    return {
        room_id: sum(
            all(position in completed_positions[room_id] for position in line)
            for line in _BINGO_LINES
        )
        for room_id in room_ids
    }


def _get_room_by_invite_code(
    db: Session,
    invite_code: str,
    *,
    lock_for_update: bool = False,
):
    lock_clause = (
        " FOR UPDATE"
        if lock_for_update and db.get_bind().dialect.name == "mysql"
        else ""
    )
    return db.execute(
        text(
            "SELECT r.room_id, r.room_name, r.status, r.max_members, r.target_bingo, "
            "(SELECT COUNT(*) FROM room_members AS members "
            " WHERE members.room_id = r.room_id) AS current_members "
            "FROM rooms AS r "
            "WHERE r.invite_code = :invite_code"
            f"{lock_clause}"
        ),
        {"invite_code": invite_code},
    ).mappings().one_or_none()


@bingo_router.post(
    "/api/rooms",
    response_model=ApiResponse[RoomCreateResponse],
    status_code=201,
    summary="빙고 방 생성",
    responses=AUTH_VALIDATION_ERROR_RESPONSES,
)
def create_room(
    payload: RoomCreateRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    # Authentication may already have opened a read-only transaction on this session.
    db.commit()
    for _ in range(5):
        invite_code = generate_invite_code()
        try:
            with db.begin():
                user_exists = db.execute(
                    text("SELECT 1 FROM users WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar_one_or_none()
                if user_exists is None:
                    raise BusinessException(ErrorCode.UNAUTHORIZED)

                invite_code_exists = db.execute(
                    text("SELECT 1 FROM rooms WHERE invite_code = :invite_code"),
                    {"invite_code": invite_code},
                ).scalar_one_or_none()
                if invite_code_exists is not None:
                    continue

                room_result = db.execute(
                    text(
                        "INSERT INTO rooms "
                        "(owner_id, room_name, invite_code, max_members, target_bingo, status, created_at) "
                        "VALUES (:owner_id, :room_name, :invite_code, :max_members, "
                        ":target_bingo, 'RECRUITING', CURRENT_TIMESTAMP)"
                    ),
                    {
                        "owner_id": user_id,
                        "room_name": payload.room_name,
                        "invite_code": invite_code,
                        "max_members": payload.max_members,
                        "target_bingo": payload.target_bingo,
                    },
                )
                room_id = room_result.lastrowid
                if room_id is None:
                    raise RuntimeError("The database did not return the new room ID.")

                db.execute(
                    text(
                        "INSERT INTO room_members (room_id, user_id, role, joined_at) "
                        "VALUES (:room_id, :user_id, 'OWNER', CURRENT_TIMESTAMP)"
                    ),
                    {"room_id": room_id, "user_id": user_id},
                )
            break
        except IntegrityError as exc:
            db.rollback()
            message = str(exc.orig)
            is_invite_code_conflict = (
                "uq_rooms_invite_code" in message or "rooms.invite_code" in message
            )
            if not is_invite_code_conflict:
                raise
    else:
        raise BusinessException(
            ErrorCode.INTERNAL_ERROR,
            "초대 코드를 생성하지 못했습니다. 다시 시도해 주세요.",
        )

    return ok(
        RoomCreateResponse(
            room_id=room_id,
            room_name=payload.room_name,
            max_members=payload.max_members,
            current_members=1,
            target_bingo=payload.target_bingo,
            status="RECRUITING",
            invite_url=build_invite_url(invite_code),
        )
    )


@bingo_router.get(
    "/api/rooms/invite/{invite_code}",
    response_model=ApiResponse[InviteValidationResponse],
    summary="초대 코드 유효성 및 방 정보 조회",
    responses=PUBLIC_ERROR_RESPONSES,
)
def get_invite_room(
    invite_code: str = Path(min_length=1, max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    room = _get_room_by_invite_code(db, invite_code)
    if room is None:
        return ok(InviteValidationResponse(valid=False, room=None))

    return ok(
        InviteValidationResponse(
            valid=True,
            room=InviteRoomInfo(
                room_id=room["room_id"],
                room_name=room["room_name"],
                status=room["status"],
                current_members=room["current_members"],
                max_members=room["max_members"],
                target_bingo=room["target_bingo"],
                achieved_bingo=_get_achieved_bingo_counts(
                    db, [room["room_id"]]
                )[room["room_id"]],
                can_join=(
                    room["status"] == "RECRUITING"
                    and room["current_members"] < room["max_members"]
                ),
            ),
        )
    )


@bingo_router.post(
    "/api/rooms/invite/{invite_code}/join",
    response_model=ApiResponse[RoomJoinResponse],
    status_code=201,
    summary="초대 코드로 방 참여",
    responses={
        200: {
            "model": ApiResponse[RoomJoinResponse],
            "description": "이미 방에 참여한 사용자",
        },
        **JOIN_ERROR_RESPONSES,
    },
)
def join_room_by_invite(
    response: Response,
    invite_code: str = Path(min_length=1, max_length=32),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    # Authentication may already have opened a read-only transaction on this session.
    db.commit()
    with db.begin():
        user_exists = db.execute(
            text("SELECT 1 FROM users WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one_or_none()
        if user_exists is None:
            raise BusinessException(ErrorCode.UNAUTHORIZED)

        room = _get_room_by_invite_code(db, invite_code, lock_for_update=True)
        if room is None:
            raise BusinessException(ErrorCode.ROOM_NOT_FOUND)

        existing_member = db.execute(
            text(
                "SELECT 1 FROM room_members "
                "WHERE room_id = :room_id AND user_id = :user_id"
            ),
            {"room_id": room["room_id"], "user_id": user_id},
        ).scalar_one_or_none()
        if existing_member is not None:
            response.status_code = 200
        else:
            if room["status"] != "RECRUITING":
                raise BusinessException(ErrorCode.ROOM_NOT_RECRUITING)
            if room["current_members"] >= room["max_members"]:
                raise BusinessException(ErrorCode.ROOM_FULL)

            db.execute(
                text(
                    "INSERT INTO room_members (room_id, user_id, role, joined_at) "
                    "VALUES (:room_id, :user_id, 'MEMBER', CURRENT_TIMESTAMP)"
                ),
                {"room_id": room["room_id"], "user_id": user_id},
            )

    return ok(RoomJoinResponse(room_id=room["room_id"]))


@router.get(
    "/api/rooms",
    response_model=ApiResponse[RoomListResponse],
    summary="내가 참여한 방 목록 조회",
    responses=AUTH_VALIDATION_ERROR_RESPONSES,
)
def get_my_rooms(
    status: RoomStatusFilter = Query(default=RoomStatusFilter.ALL),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    filters = "mine.user_id = :user_id"
    params: dict[str, int | str] = {"user_id": user_id}
    if status != RoomStatusFilter.ALL:
        filters += " AND r.status = :status"
        params["status"] = status.value

    total_count = db.execute(
        text(
            "SELECT COUNT(DISTINCT r.room_id) "
            "FROM rooms AS r "
            "JOIN room_members AS mine ON mine.room_id = r.room_id "
            f"WHERE {filters}"
        ),
        params,
    ).scalar_one()

    page_params = {
        **params,
        "limit": size,
        "offset": (page - 1) * size,
    }
    rooms = db.execute(
        text(
            "SELECT r.room_id, r.room_name, r.status, r.max_members, r.target_bingo, "
            "(SELECT COUNT(*) FROM room_members AS members "
            " WHERE members.room_id = r.room_id) AS current_members, "
            "(SELECT COUNT(*) FROM bingo_boards AS boards "
            " JOIN bingo_cells AS cells ON cells.board_id = boards.board_id "
            " WHERE boards.room_id = r.room_id AND cells.status = 'COMPLETED') "
            " AS completed_cells, "
            "r.invite_code "
            "FROM rooms AS r "
            "JOIN room_members AS mine ON mine.room_id = r.room_id "
            f"WHERE {filters} "
            "ORDER BY r.created_at DESC, r.room_id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        page_params,
    ).mappings().all()

    room_ids = [room["room_id"] for room in rooms]
    achieved_bingo_by_room = _get_achieved_bingo_counts(db, room_ids)

    return ok(
        RoomListResponse(
            total_count=total_count,
            page=page,
            size=size,
            rooms=[
                {
                    "room_id": room["room_id"],
                    "room_name": room["room_name"],
                    "status": room["status"],
                    "current_members": room["current_members"],
                    "max_members": room["max_members"],
                    "target_bingo": room["target_bingo"],
                    "achieved_bingo": achieved_bingo_by_room[room["room_id"]],
                    "completed_cells": room["completed_cells"],
                    "total_cells": 9,
                    "invite_url": build_invite_url(room["invite_code"]),
                }
                for room in rooms
            ],
        )
    )
