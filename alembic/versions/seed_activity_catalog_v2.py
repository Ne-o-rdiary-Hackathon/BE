"""Seed the activity category and activity catalog.

Revision ID: 2d6f9c4a8b31
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "2d6f9c4a8b31"
down_revision: Union[str, None] = "8f21c0a3d7b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORY_SEEDS = (
    (
        "스포츠",
        (
            (
                "실내 스포츠",
                ("볼링", "탁구", "배드민턴", "테니스", "스쿼시", "당구", "클라이밍"),
            ),
            (
                "야외 스포츠",
                ("러닝하기", "등산하기", "자전거 타기", "인라인스케이트", "롤러스케이트", "스케이트보드"),
            ),
            ("생활 운동", ("산책하기", "수영", "요가", "필라테스", "홈트레이닝", "줄넘기")),
        ),
    ),
    (
        "취미",
        (
            (
                "공예·DIY",
                ("도자기 만들기", "향수 만들기", "비즈 공예", "뜨개질", "꽃꽂이", "캔들 만들기", "키링 만들기", "터프팅"),
            ),
            (
                "미술·창작",
                ("그림 그리기", "수채화 그리기", "컬러링북", "사진 촬영", "필름 카메라", "디지털 드로잉", "글쓰기"),
            ),
            (
                "음악·퍼포먼스",
                ("악기 연주하기", "노래방 가기", "댄스 챌린지", "랜덤 플레이 댄스", "보컬 레슨", "악기 합주"),
            ),
        ),
    ),
    (
        "여가·문화생활",
        (
            (
                "문화생활",
                ("영화 보기", "전시회 관람", "미술관 가기", "공연 관람", "뮤지컬 관람", "연극 관람", "독립영화 보기", "팝업스토어 구경하기"),
            ),
            (
                "실내 놀거리",
                ("보드게임 카페", "방탈출 카페", "오락실 가기", "만화카페 가기", "코인 노래방", "이색 체험 공간 방문하기"),
            ),
            (
                "야외 여가",
                ("공원 산책하기", "피크닉", "한강 나들이", "야경 명소 가기", "야시장 구경하기", "플리마켓 방문하기", "놀이공원 가기"),
            ),
        ),
    ),
    (
        "맛집·카페",
        (
            (
                "맛집 탐방",
                ("맛집 투어", "빵지순례", "디저트 투어", "브런치 먹기", "전통시장 먹거리 탐방", "길거리 음식 먹기", "새로운 음식 도전하기", "편의점 신상 먹기"),
            ),
            (
                "카페 탐방",
                ("카페 투어", "북카페 가기", "디저트 카페 가기", "이색 카페 가기", "홈카페 즐기기"),
            ),
            (
                "요리·음료 만들기",
                ("함께 요리해 먹기", "베이킹", "쿠키 만들기", "케이크 만들기", "파스타 만들기", "랜덤 재료 요리하기", "커피 핸드드립", "칵테일 만들기"),
            ),
        ),
    ),
    (
        "나들이·여행",
        (
            (
                "근교 나들이",
                ("새로운 동네 가보기", "동네 탐방하기", "근교 나들이", "드라이브", "바다 보러 가기", "산으로 떠나기", "지역 명소 방문하기", "기차역 주변 탐방하기"),
            ),
            (
                "여행",
                ("당일치기 여행", "국내 소도시 여행", "즉흥 여행", "기차 여행", "캠핑", "차박", "호캉스", "무계획 여행"),
            ),
            (
                "야외 탐방",
                ("골목길 사진 찍기", "숨은 맛집 찾기", "새로운 장소 찾아보기", "건축물 구경하기", "랜덤 역에서 내리기", "일출 보러 가기"),
            ),
        ),
    ),
    (
        "일상·이색 활동",
        (
            (
                "친구와 함께하는 활동",
                ("서로의 옷 골라주기", "랜덤 선물 교환하기", "서로 사진 찍어주기", "인생네컷 찍기", "서로의 버킷리스트 해보기", "서로에게 편지 쓰기", "새로운 취미 함께 도전하기"),
            ),
            (
                "소소한 도전",
                ("만 원으로 하루 보내기", "랜덤 메뉴 정해서 먹기", "하루 브이로그 찍기", "하루 동안 사진 작가 되기", "평소 안 입는 스타일 입기", "하루 동안 휴대폰 없이 놀기", "새로운 사람과 대화하기"),
            ),
            (
                "운세·체험",
                ("타로 보기", "운세 보기", "원데이 클래스 참여하기", "사격 체험", "승마 체험", "서핑 배우기", "서로의 취향 블라인드 테스트"),
            ),
        ),
    ),
)


def _category_names() -> list[str]:
    names = []
    for parent_name, children in _CATEGORY_SEEDS:
        names.append(parent_name)
        names.extend(child_name for child_name, _ in children)
    return names


def _assert_category_names_are_available(connection: sa.Connection) -> None:
    names = _category_names()
    existing = connection.execute(
        sa.text(
            "SELECT category_name FROM activity_categories "
            "WHERE category_name IN :names"
        ).bindparams(sa.bindparam("names", type_=sa.String(), expanding=True)),
        {"names": names},
    ).scalars().all()
    if existing:
        raise RuntimeError(
            "Activity seed migration stopped because category names already exist: "
            + ", ".join(sorted(set(existing)))
        )


def upgrade() -> None:
    if not context.is_offline_mode():
        _assert_category_names_are_available(op.get_bind())

    for parent_name, children in _CATEGORY_SEEDS:
        op.execute(
            sa.text(
                "INSERT INTO activity_categories (parent_id, category_name) "
                "VALUES (NULL, :parent_name)"
            ).bindparams(parent_name=parent_name)
        )

        for child_name, activity_names in children:
            op.execute(
                sa.text(
                    "INSERT INTO activity_categories (parent_id, category_name) "
                    "SELECT parent_category.category_id, :child_name "
                    "FROM activity_categories AS parent_category "
                    "WHERE parent_category.category_name = :parent_name "
                    "AND parent_category.parent_id IS NULL"
                ).bindparams(child_name=child_name, parent_name=parent_name)
            )

            for activity_name in activity_names:
                op.execute(
                    sa.text(
                        "INSERT INTO activities (category_id, activity_name) "
                        "SELECT child_category.category_id, :activity_name "
                        "FROM activity_categories AS child_category "
                        "JOIN activity_categories AS parent_category "
                        "ON parent_category.category_id = child_category.parent_id "
                        "WHERE child_category.category_name = :child_name "
                        "AND parent_category.category_name = :parent_name "
                        "AND parent_category.parent_id IS NULL"
                    ).bindparams(
                        activity_name=activity_name,
                        child_name=child_name,
                        parent_name=parent_name,
                    )
                )


def _assert_seed_activities_are_unused(connection: sa.Connection) -> None:
    child_names = [
        child_name
        for _, children in _CATEGORY_SEEDS
        for child_name, _ in children
    ]
    parent_names = [parent_name for parent_name, _ in _CATEGORY_SEEDS]
    referenced_count = connection.execute(
        sa.text(
            "SELECT COUNT(DISTINCT activity.activity_id) "
            "FROM activities AS activity "
            "JOIN activity_categories AS child_category "
            "ON child_category.category_id = activity.category_id "
            "JOIN activity_categories AS parent_category "
            "ON parent_category.category_id = child_category.parent_id "
            "WHERE child_category.category_name IN :child_names "
            "AND parent_category.category_name IN :parent_names "
            "AND parent_category.parent_id IS NULL "
            "AND ("
            "EXISTS (SELECT 1 FROM user_response_activities AS selected "
            "WHERE selected.activity_id = activity.activity_id) "
            "OR EXISTS (SELECT 1 FROM bingo_cells AS cell "
            "WHERE cell.activity_id = activity.activity_id)"
            ")"
        ).bindparams(
            sa.bindparam("child_names", type_=sa.String(), expanding=True),
            sa.bindparam("parent_names", type_=sa.String(), expanding=True),
        ),
        {"child_names": child_names, "parent_names": parent_names},
    ).scalar_one()
    if referenced_count:
        raise RuntimeError(
            "Cannot downgrade activity seed data while seeded activities "
            "are used by responses or bingo cells."
        )


def downgrade() -> None:
    if not context.is_offline_mode():
        _assert_seed_activities_are_unused(op.get_bind())

    for parent_name, children in _CATEGORY_SEEDS:
        for child_name, activity_names in children:
            op.execute(
                sa.text(
                    "DELETE activity "
                    "FROM activities AS activity "
                    "JOIN activity_categories AS child_category "
                    "ON child_category.category_id = activity.category_id "
                    "JOIN activity_categories AS parent_category "
                    "ON parent_category.category_id = child_category.parent_id "
                    "WHERE child_category.category_name = :child_name "
                    "AND parent_category.category_name = :parent_name "
                    "AND parent_category.parent_id IS NULL "
                    "AND activity.activity_name IN :activity_names"
                )
                .bindparams(sa.bindparam("activity_names", type_=sa.String(), expanding=True))
                .bindparams(
                    child_name=child_name,
                    parent_name=parent_name,
                    activity_names=activity_names,
                )
            )

            op.execute(
                sa.text(
                    "DELETE child_category "
                    "FROM activity_categories AS child_category "
                    "JOIN activity_categories AS parent_category "
                    "ON parent_category.category_id = child_category.parent_id "
                    "LEFT JOIN activities AS activity "
                    "ON activity.category_id = child_category.category_id "
                    "WHERE child_category.category_name = :child_name "
                    "AND parent_category.category_name = :parent_name "
                    "AND parent_category.parent_id IS NULL "
                    "AND activity.activity_id IS NULL"
                ).bindparams(child_name=child_name, parent_name=parent_name)
            )

        op.execute(
            sa.text(
                "DELETE parent_category "
                "FROM activity_categories AS parent_category "
                "LEFT JOIN activity_categories AS child_category "
                "ON child_category.parent_id = parent_category.category_id "
                "WHERE parent_category.category_name = :parent_name "
                "AND parent_category.parent_id IS NULL "
                "AND child_category.category_id IS NULL"
            ).bindparams(parent_name=parent_name)
        )
