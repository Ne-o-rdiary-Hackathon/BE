import asyncio
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import bingo as bingo_api
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.activity import Activity, ActivityCategory, UserResponse, UserResponseActivity
from app.models.bingo import BingoCell
from app.models.room import Room, RoomMember
from app.models.user import User
from app.services.bingo_service import BingoService, completed_lines
from app.services.image_storage import LocalImageStorage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
OWNER, MEMBER, OUTSIDER = 1, 2, 3


@pytest.fixture
def env(tmp_path: Path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        # users 모델의 MySQL 전용 server_default(ON UPDATE)는 SQLite에서 못 쓰므로 직접 만듭니다.
        conn.execute(text(
            "CREATE TABLE users (user_id INTEGER PRIMARY KEY, kakao_id BIGINT NOT NULL, "
            "nickname VARCHAR(30) NOT NULL, profile_image_url VARCHAR(1000), "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        ))
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "users"])
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        db.add_all([
            User(user_id=OWNER, kakao_id=101, nickname="김민지", profile_image_url="https://p/1.jpg"),
            User(user_id=MEMBER, kakao_id=102, nickname="이서현", profile_image_url=None),
            User(user_id=OUTSIDER, kakao_id=103, nickname="외부인"),
        ])
        db.add(Room(room_id=1, owner_id=OWNER, room_name="퇴근 후 도파민 수혈단",
                    invite_code="abc", max_members=4, target_bingo=3))
        db.add_all([
            RoomMember(room_id=1, user_id=OWNER, role="OWNER"),
            RoomMember(room_id=1, user_id=MEMBER, role="MEMBER"),
        ])
        db.add(ActivityCategory(category_id=1, category_name="스포츠"))
        db.add_all([Activity(activity_id=i, category_id=1, activity_name=f"활동{i}") for i in range(1, 13)])
        db.flush()
        # 활동7: 둘 다 하고 싶어요(2점) / 활동8: 1점 / 활동9: 하고 싶어요1 + 질렸어요1 = 0점 / 활동10: 질렸어요(-1점)
        for response_id, user_id, picks in (
            (1, OWNER, [(7, "DESIRED"), (8, "DESIRED"), (9, "DESIRED")]),
            (2, MEMBER, [(7, "DESIRED"), (9, "BORED"), (10, "BORED")]),
        ):
            db.add(UserResponse(response_id=response_id, room_id=1, user_id=user_id, status="SUBMITTED"))
            db.flush()
            db.add_all([UserResponseActivity(response_id=response_id, activity_id=a, selection_type=s)
                        for a, s in picks])
        db.commit()

    storage = LocalImageStorage(str(tmp_path))
    state = {"user_id": OWNER}

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        with Session() as db:
            return db.get(User, state["user_id"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[bingo_api.get_bingo_service] = lambda: BingoService(next(override_db()), storage)
    yield {"Session": Session, "state": state, "tmp": tmp_path}
    app.dependency_overrides.clear()


def call(method: str, path: str, **kwargs) -> httpx.Response:
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            return await c.request(method, path, **kwargs)

    return asyncio.run(request())


def verify(cell_id: int, data: bytes = PNG) -> httpx.Response:
    return call("POST", f"/api/rooms/1/bingo-board/cells/{cell_id}/verification",
                files={"image": ("photo.png", data, "image/png")})


def cell_at(env, position: int) -> int:
    with env["Session"]() as db:
        return db.scalar(select(BingoCell.cell_id).where(BingoCell.position == position))


def test_completed_lines() -> None:
    assert completed_lines({0, 1, 2}) == [(0, 1, 2)]
    assert completed_lines({0, 4, 8, 2, 6}) == [(0, 4, 8), (2, 4, 6)]
    assert completed_lines({0, 1}) == []


def test_create_board_by_owner(env) -> None:
    res = call("POST", "/api/rooms/1/bingo-board")
    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["room_status"] == "IN_PROGRESS"
    assert (data["target_bingo"], data["achieved_bingo"], data["completed_cells"]) == (3, 0, 0)
    assert data["bingo_cell_ids"] == []
    assert [c["position"] for c in data["cells"]] == list(range(9))
    assert all(c["status"] == "PENDING" and c["image_url"] is None for c in data["cells"])

    names = {c["activity_name"]: c for c in data["cells"]}
    assert names["활동7"]["position"] == 4 and names["활동7"]["score"] == 2  # 1위는 가운데
    assert names["활동8"]["score"] == 1
    assert "활동10" not in names  # 질렸어요(-1점)는 0점 활동보다 뒤로 밀려 빠짐


def test_create_board_rules(env) -> None:
    env["state"]["user_id"] = MEMBER
    assert call("POST", "/api/rooms/1/bingo-board").json()["error"]["code"] == "NOT_ROOM_OWNER"

    env["state"]["user_id"] = OWNER
    assert call("POST", "/api/rooms/1/bingo-board").status_code == 200
    res = call("POST", "/api/rooms/1/bingo-board")
    assert res.status_code == 409 and res.json()["error"]["code"] == "BOARD_ALREADY_EXISTS"

    assert call("POST", "/api/rooms/99/bingo-board").json()["error"]["code"] == "ROOM_NOT_FOUND"


def test_get_board_requires_membership_and_board(env) -> None:
    assert call("GET", "/api/rooms/1/bingo-board").json()["error"]["code"] == "BOARD_NOT_FOUND"
    call("POST", "/api/rooms/1/bingo-board")

    env["state"]["user_id"] = OUTSIDER
    res = call("GET", "/api/rooms/1/bingo-board")
    assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_ROOM_MEMBER"


def test_verify_and_bingo_judgement(env) -> None:
    call("POST", "/api/rooms/1/bingo-board")
    row0 = [cell_at(env, p) for p in (0, 1, 2)]

    first = verify(row0[0]).json()["data"]
    assert first["cell"]["status"] == "COMPLETED"
    assert first["cell"]["image_url"].startswith("/uploads/verifications/1/")
    assert (first["achieved_bingo"], first["completed_cells"]) == (0, 1)
    assert first["new_bingo_cell_ids"] == [] and first["room_completed"] is False

    env["state"]["user_id"] = MEMBER
    verify(row0[1])
    third = verify(row0[2]).json()["data"]
    assert third["achieved_bingo"] == 1
    assert third["new_bingo_cell_ids"] == row0
    assert third["bingo_cell_ids"] == row0

    # 사진이 실제로 저장됐는지
    key = third["cell"]["image_url"].removeprefix("/uploads/")
    assert (env["tmp"] / key).read_bytes() == PNG

    board = call("GET", "/api/rooms/1/bingo-board").json()["data"]
    assert board["achieved_bingo"] == 1 and board["completed_cells"] == 3
    assert board["bingo_cell_ids"] == row0


def test_verify_errors(env) -> None:
    call("POST", "/api/rooms/1/bingo-board")
    cell_id = cell_at(env, 0)

    res = verify(cell_id, b"not an image at all")
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_IMAGE"
    assert not any(env["tmp"].rglob("*.*"))  # 실패한 요청은 저장하지 않음

    assert verify(cell_id).status_code == 200
    res = verify(cell_id)
    assert res.status_code == 409 and res.json()["error"]["code"] == "CELL_ALREADY_COMPLETED"

    assert verify(99999).json()["error"]["code"] == "CELL_NOT_FOUND"

    env["state"]["user_id"] = OUTSIDER
    assert verify(cell_at(env, 1)).json()["error"]["code"] == "NOT_ROOM_MEMBER"


def test_verify_rejects_large_image(env, monkeypatch) -> None:
    call("POST", "/api/rooms/1/bingo-board")
    monkeypatch.setattr(bingo_api, "MAX_IMAGE_BYTES", 10)
    res = verify(cell_at(env, 0))
    assert res.status_code == 413 and res.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_room_completes_at_target_and_result(env) -> None:
    with env["Session"]() as db:
        db.get(Room, 1).target_bingo = 1
        db.commit()
    call("POST", "/api/rooms/1/bingo-board")
    col1 = [cell_at(env, p) for p in (1, 4, 7)]

    verify(col1[0])
    env["state"]["user_id"] = MEMBER
    verify(col1[1])
    last = verify(col1[2]).json()["data"]
    assert last["room_completed"] is True
    assert last["new_bingo_cell_ids"] == col1

    # 목표 달성 후에는 더 인증할 수 없음
    res = verify(cell_at(env, 0))
    assert res.json()["error"]["code"] == "ROOM_NOT_IN_PROGRESS"

    result = call("GET", "/api/rooms/1/result").json()["data"]
    assert result["room_name"] == "퇴근 후 도파민 수혈단"
    assert (result["target_bingo"], result["achieved_bingo"], result["completed_cells"]) == (1, 1, 3)
    assert result["bingo_cell_ids"] == col1
    assert result["members"] == [
        {"nickname": "김민지", "profile_image_url": "https://p/1.jpg", "verified_count": 1},
        {"nickname": "이서현", "profile_image_url": None, "verified_count": 2},
    ]
    assert len(result["cells"]) == 9


def test_board_includes_room_name_and_members(env) -> None:
    data = call("POST", "/api/rooms/1/bingo-board").json()["data"]
    assert data["room_name"] == "퇴근 후 도파민 수혈단"
    assert data["members"] == [
        {"user_id": OWNER, "nickname": "김민지", "profile_image_url": "https://p/1.jpg", "role": "OWNER"},
        {"user_id": MEMBER, "nickname": "이서현", "profile_image_url": None, "role": "MEMBER"},
    ]

    env["state"]["user_id"] = MEMBER
    assert call("GET", "/api/rooms/1/bingo-board").json()["data"]["members"] == data["members"]



def test_board_uses_ai_mission_text(env, monkeypatch) -> None:
    from app.services import bingo_service

    calls = []

    def fake_write_missions(names):
        calls.append(list(names))
        # 첫 칸만 AI 문구가 왔다고 가정 (나머지는 write_missions가 활동 이름을 돌려준 상황)
        return [f"{names[0]} 완등"] + list(names[1:])

    monkeypatch.setattr(bingo_service, "write_missions", fake_write_missions)
    data = call("POST", "/api/rooms/1/bingo-board").json()["data"]

    # AI에는 고른 9개 활동 이름이 1위(가운데 칸)부터 순서대로 전달됨
    assert len(calls) == 1 and len(calls[0]) == 9
    center = next(c for c in data["cells"] if c["position"] == 4)
    assert calls[0][0] == center["activity_name"]
    assert center["mission_text"] == f"{center['activity_name']} 완등"
    assert all(c["mission_text"] == c["activity_name"] for c in data["cells"] if c["position"] != 4)

    # DB에 저장돼서 조회·인증·결과에서도 같은 문구
    board = call("GET", "/api/rooms/1/bingo-board").json()["data"]
    assert next(c for c in board["cells"] if c["position"] == 4)["mission_text"] == center["mission_text"]
    verified = verify(center["cell_id"]).json()["data"]
    assert verified["cell"]["mission_text"] == center["mission_text"]
    result = call("GET", "/api/rooms/1/result").json()["data"]
    assert next(c for c in result["cells"] if c["position"] == 4)["mission_text"] == center["mission_text"]


def test_old_board_without_mission_text_uses_activity_name(env) -> None:
    call("POST", "/api/rooms/1/bingo-board")
    with env["Session"]() as db:
        db.execute(text("UPDATE bingo_cells SET mission_text = NULL"))
        db.commit()
    cells = call("GET", "/api/rooms/1/bingo-board").json()["data"]["cells"]
    assert all(c["mission_text"] == c["activity_name"] for c in cells)
