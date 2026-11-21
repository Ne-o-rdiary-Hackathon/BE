import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.api.home_dependencies import get_current_user_id
from app.common import BusinessException, ErrorCode, ok
from app.db.session import get_db
from app.schemas.activities import (
    ActivityCategory,
    ActivityCatalogResponse,
    ActivityItem,
    ActivitySubmissionRequest,
    ActivitySubmissionResponse,
    ActivitySubcategory,
)
from app.schemas.common import (
    ApiResponse,
    JOIN_ERROR_RESPONSES,
    PUBLIC_ERROR_RESPONSES,
)

router = APIRouter(tags=["활동"])
log = logging.getLogger("backend.activities")


def try_create_board(db: Session, room_id: int) -> bool:
    """마지막 제출 직후 빙고판 자동 생성을 시도합니다.

    자동 생성이 실패해도 방금 저장한 제출은 그대로 두고, 방장이 버튼으로 다시 만들 수 있습니다.
    """
    from app.services.bingo_service import BingoService
    from app.services.image_storage import get_image_storage

    try:
        return BingoService(db, get_image_storage()).create_board_if_ready(room_id)
    except Exception:
        db.rollback()
        log.exception("빙고판 자동 생성 실패 (room_id=%s)", room_id)
        return False


@router.get(
    "/api/v1/activities",
    response_model=ApiResponse[ActivityCatalogResponse],
    summary="활동 카테고리 및 목록 조회",
    responses=PUBLIC_ERROR_RESPONSES,
)
def get_activities(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        text(
            "SELECT parent.category_id AS parent_id, parent.category_name AS parent_name, "
            "child.category_id AS child_id, child.category_name AS child_name, "
            "activity.activity_id, activity.activity_name "
            "FROM activity_categories AS parent "
            "LEFT JOIN activity_categories AS child "
            "ON child.parent_id = parent.category_id AND child.is_active = 1 "
            "LEFT JOIN activities AS activity "
            "ON activity.category_id = child.category_id AND activity.is_active = 1 "
            "WHERE parent.parent_id IS NULL AND parent.is_active = 1 "
            "ORDER BY parent.category_id, child.category_id, activity.activity_id"
        )
    ).mappings()

    categories: dict[int, ActivityCategory] = {}
    subcategories: dict[int, ActivitySubcategory] = {}
    for row in rows:
        parent_id = row["parent_id"]
        category = categories.get(parent_id)
        if category is None:
            category = ActivityCategory(
                category_id=parent_id,
                category_name=row["parent_name"],
                subcategories=[],
            )
            categories[parent_id] = category

        child_id = row["child_id"]
        if child_id is None:
            continue

        subcategory = subcategories.get(child_id)
        if subcategory is None:
            subcategory = ActivitySubcategory(
                category_id=child_id,
                category_name=row["child_name"],
                activities=[],
            )
            subcategories[child_id] = subcategory
            category.subcategories.append(subcategory)

        if row["activity_id"] is not None:
            subcategory.activities.append(
                ActivityItem(
                    activity_id=row["activity_id"],
                    activity_name=row["activity_name"],
                )
            )

    return ok(ActivityCatalogResponse(categories=list(categories.values())))


@router.post(
    "/api/v1/rooms/{roomId}/responses/me/submit",
    response_model=ApiResponse[ActivitySubmissionResponse],
    summary="활동 선택 최종 제출",
    responses={
        **JOIN_ERROR_RESPONSES,
        403: {"model": ApiResponse[None], "description": "해당 방의 참여자가 아닙니다."},
    },
)
def submit_activity_response(
    payload: ActivitySubmissionRequest,
    room_id: Annotated[int, Path(alias="roomId", gt=0)],
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    lock_clause = " FOR UPDATE" if db.get_bind().dialect.name == "mysql" else ""
    room = db.execute(
        text(
            f"SELECT room_id, status FROM rooms "
            f"WHERE room_id = :room_id{lock_clause}"
        ),
        {"room_id": room_id},
    ).mappings().one_or_none()
    if room is None:
        raise BusinessException(ErrorCode.ROOM_NOT_FOUND)

    is_member = db.execute(
        text(
            "SELECT 1 FROM room_members "
            "WHERE room_id = :room_id AND user_id = :user_id"
        ),
        {"room_id": room_id, "user_id": user_id},
    ).scalar_one_or_none()
    if is_member is None:
        raise BusinessException(ErrorCode.FORBIDDEN)
    if room["status"] != "RECRUITING":
        raise BusinessException(ErrorCode.ROOM_NOT_RECRUITING)

    activity_ids = payload.desired_activity_ids + payload.bored_activity_ids
    if activity_ids:
        active_activity_ids = set(
            db.execute(
                text(
                    "SELECT activity_id FROM activities "
                    "WHERE is_active = 1 AND activity_id IN :activity_ids"
                ).bindparams(bindparam("activity_ids", expanding=True)),
                {"activity_ids": activity_ids},
            ).scalars()
        )
        if active_activity_ids != set(activity_ids):
            raise BusinessException(
                ErrorCode.INVALID_INPUT,
                "존재하지 않거나 비활성화된 활동이 포함되어 있습니다.",
            )

    response = db.execute(
        text(
            "SELECT response_id FROM user_responses "
            "WHERE room_id = :room_id AND user_id = :user_id"
        ),
        {"room_id": room_id, "user_id": user_id},
    ).scalar_one_or_none()
    if response is None:
        insert_result = db.execute(
            text(
                "INSERT INTO user_responses "
                "(room_id, user_id, status, submitted_at, created_at) "
                "VALUES (:room_id, :user_id, 'SUBMITTED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"room_id": room_id, "user_id": user_id},
        )
        response_id = insert_result.lastrowid
        if response_id is None:
            raise RuntimeError("The database did not return the new response ID.")
    else:
        response_id = response
        db.execute(
            text("DELETE FROM user_response_activities WHERE response_id = :response_id"),
            {"response_id": response_id},
        )
        db.execute(
            text(
                "UPDATE user_responses SET status = 'SUBMITTED', "
                "submitted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                "WHERE response_id = :response_id"
            ),
            {"response_id": response_id},
        )

    selections = [
        {
            "response_id": response_id,
            "activity_id": activity_id,
            "selection_type": selection_type,
        }
        for selection_type, selected_ids in (
            ("DESIRED", payload.desired_activity_ids),
            ("BORED", payload.bored_activity_ids),
        )
        for activity_id in selected_ids
    ]
    if selections:
        db.execute(
            text(
                "INSERT INTO user_response_activities "
                "(response_id, activity_id, selection_type, created_at) "
                "VALUES (:response_id, :activity_id, :selection_type, CURRENT_TIMESTAMP)"
            ),
            selections,
        )

    remaining_members = db.execute(
        text(
            "SELECT COUNT(*) FROM room_members AS members "
            "LEFT JOIN user_responses AS responses "
            "ON responses.room_id = members.room_id "
            "AND responses.user_id = members.user_id "
            "AND responses.status = 'SUBMITTED' "
            "WHERE members.room_id = :room_id AND responses.response_id IS NULL"
        ),
        {"room_id": room_id},
    ).scalar_one()
    db.commit()

    # 정원이 다 찼고 이번 제출로 전원이 제출했으면 빙고판을 바로 만듭니다.
    board_created = remaining_members == 0 and try_create_board(db, room_id)

    return ok(
        ActivitySubmissionResponse(
            status="SUBMITTED",
            all_members_submitted=remaining_members == 0,
            board_created=board_created,
        )
    )
