from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.home_dependencies as home_dependencies
from app.api.home_dependencies import get_current_user_id
from app.core.invites import INVITE_URL_PREFIX, build_invite_url
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users ("
            "user_id INTEGER PRIMARY KEY, nickname VARCHAR(30) NOT NULL, "
            "profile_image_url VARCHAR(500))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE rooms ("
            "room_id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, "
            "room_name VARCHAR(20) NOT NULL, invite_code VARCHAR(32) NOT NULL, "
            "max_members INTEGER NOT NULL, target_bingo INTEGER NOT NULL, "
            "status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE room_members ("
            "room_member_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'MEMBER', "
            "joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE bingo_boards ("
            "board_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE bingo_cells ("
            "cell_id INTEGER PRIMARY KEY, board_id INTEGER NOT NULL, "
            "position INTEGER NOT NULL, status VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES "
            "(1, '김민지', 'https://example.com/profile.jpg'), "
            "(2, '사용자2', NULL), "
            "(3, '사용자3', NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO rooms VALUES "
            "(1, 1, '퇴근 후 모임', '8X92KABC', 4, 3, 'IN_PROGRESS', '2026-11-02'), "
            "(2, 1, '주말 모임', 'B3J9M2QX', 5, 2, 'RECRUITING', '2026-11-01'), "
            "(3, 2, '참여 가능한 방', 'K7PQ21NM', 3, 3, 'RECRUITING', '2026-10-31'), "
            "(4, 2, '정원이 찬 방', 'F4LLFULL', 2, 2, 'RECRUITING', '2026-10-30')"
        )
        connection.exec_driver_sql(
            "INSERT INTO room_members (room_member_id, room_id, user_id) VALUES "
            "(1, 1, 1), (2, 1, 2), (3, 2, 1), (4, 3, 2), "
            "(5, 4, 2), (6, 4, 3)"
        )
        connection.exec_driver_sql("INSERT INTO bingo_boards VALUES (10, 1)")
        connection.exec_driver_sql(
            "INSERT INTO bingo_cells VALUES "
            "(1, 10, 0, 'COMPLETED'), (2, 10, 1, 'COMPLETED'), "
            "(3, 10, 2, 'COMPLETED'), (4, 10, 3, 'COMPLETED'), "
            "(5, 10, 4, 'COMPLETED'), (6, 10, 5, 'COMPLETED'), "
            "(7, 10, 6, 'PENDING'), (8, 10, 7, 'PENDING'), "
            "(9, 10, 8, 'PENDING')"
        )

    def override_get_db() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: 1
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_get_my_rooms_returns_member_counts_and_bingo_progress(client: TestClient) -> None:
    response = client.get("/api/rooms?status=ALL&page=1&size=10")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "error": None,
        "data": {
        "total_count": 2,
        "page": 1,
        "size": 10,
        "rooms": [
            {
                "room_id": 1,
                "room_name": "퇴근 후 모임",
                "status": "IN_PROGRESS",
                "current_members": 2,
                "max_members": 4,
                "target_bingo": 3,
                "achieved_bingo": 2,
                "completed_cells": 6,
                "total_cells": 9,
                "invite_url": build_invite_url("8X92KABC"),
            },
            {
                "room_id": 2,
                "room_name": "주말 모임",
                "status": "RECRUITING",
                "current_members": 1,
                "max_members": 5,
                "target_bingo": 2,
                "achieved_bingo": 0,
                "completed_cells": 0,
                "total_cells": 9,
                "invite_url": build_invite_url("B3J9M2QX"),
            },
        ],
        },
    }


def test_get_my_rooms_filters_and_paginates(client: TestClient) -> None:
    response = client.get("/api/rooms?status=RECRUITING&page=1&size=1")

    assert response.status_code == 200
    assert response.json()["data"]["total_count"] == 1
    assert [room["room_id"] for room in response.json()["data"]["rooms"]] == [2]


def test_create_room_registers_owner_and_returns_invite_url(client: TestClient) -> None:
    response = client.post(
        "/api/rooms",
        json={
            "room_name": "퇴근 후 도파민 수혈단",
            "max_members": 4,
            "target_bingo": 3,
        },
    )

    assert response.status_code == 201
    envelope = response.json()
    assert envelope["success"] is True
    assert envelope["error"] is None
    data = envelope["data"]
    assert set(data) == {
        "room_id",
        "room_name",
        "max_members",
        "current_members",
        "target_bingo",
        "status",
        "invite_url",
    }
    assert data["room_id"] == 5
    assert data["room_name"] == "퇴근 후 도파민 수혈단"
    assert data["max_members"] == 4
    assert data["current_members"] == 1
    assert data["target_bingo"] == 3
    assert data["status"] == "RECRUITING"
    assert data["invite_url"].startswith(f"{INVITE_URL_PREFIX}/")
    invite_code = data["invite_url"].rsplit("/", 1)[1]
    assert len(invite_code) == 8
    assert invite_code.isalnum() and invite_code == invite_code.upper()

    rooms_response = client.get("/api/rooms")
    created_room = next(
        room
        for room in rooms_response.json()["data"]["rooms"]
        if room["room_id"] == data["room_id"]
    )
    assert created_room["current_members"] == 1


def test_create_room_rejects_values_outside_schema_constraints(client: TestClient) -> None:
    response = client.post(
        "/api/rooms",
        json={"room_name": "방", "max_members": 1, "target_bingo": 4},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_invite_lookup_returns_room_preview_or_invalid_result(client: TestClient) -> None:
    valid_response = client.get("/api/rooms/invite/K7PQ21NM")
    full_response = client.get("/api/rooms/invite/F4LLFULL")
    invalid_response = client.get("/api/rooms/invite/AAAAAAAA")

    assert valid_response.status_code == 200
    assert valid_response.json()["data"] == {
        "valid": True,
        "room": {
            "room_id": 3,
            "room_name": "참여 가능한 방",
            "status": "RECRUITING",
            "current_members": 1,
            "max_members": 3,
            "target_bingo": 3,
            "achieved_bingo": 0,
            "can_join": True,
        },
    }
    in_progress_response = client.get("/api/rooms/invite/8X92KABC")
    assert in_progress_response.json()["data"]["room"]["achieved_bingo"] == 2
    assert full_response.json()["data"]["room"]["can_join"] is False
    assert invalid_response.status_code == 200
    assert invalid_response.json()["data"] == {"valid": False, "room": None}


def test_join_by_invite_adds_member_and_is_idempotent(client: TestClient) -> None:
    path = "/api/rooms/invite/K7PQ21NM/join"

    first_response = client.post(path)
    second_response = client.post(path)

    assert first_response.status_code == 201
    assert first_response.json()["data"] == {"room_id": 3}
    assert second_response.status_code == 200
    assert second_response.json()["data"] == {"room_id": 3}

    rooms_response = client.get("/api/rooms")
    joined_room = next(
        room
        for room in rooms_response.json()["data"]["rooms"]
        if room["room_id"] == 3
    )
    assert joined_room["current_members"] == 2


def test_join_by_invite_rejects_missing_or_full_rooms(client: TestClient) -> None:
    missing_response = client.post("/api/rooms/invite/AAAAAAAA/join")
    full_response = client.post("/api/rooms/invite/F4LLFULL/join")

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "ROOM_NOT_FOUND"
    assert full_response.status_code == 409
    assert full_response.json()["error"]["code"] == "ROOM_FULL"


def test_join_by_invite_rejects_non_recruiting_rooms(client: TestClient) -> None:
    current_user_override = app.dependency_overrides[get_current_user_id]
    app.dependency_overrides[get_current_user_id] = lambda: 3
    try:
        response = client.post("/api/rooms/invite/8X92KABC/join")
    finally:
        app.dependency_overrides[get_current_user_id] = current_user_override

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROOM_NOT_RECRUITING"


def test_home_endpoints_require_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(get_current_user_id)

    response = client.get("/api/rooms")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ACCESS_TOKEN"


def test_home_endpoints_use_the_authenticated_login_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides.pop(get_current_user_id)
    monkeypatch.setattr(
        home_dependencies,
        "get_current_user",
        lambda request, credentials, db: SimpleNamespace(user_id=1),
    )

    response = client.get("/api/rooms")

    assert response.status_code == 200


def test_dev_auth_header_is_enabled_only_in_development(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides.pop(get_current_user_id)
    monkeypatch.setattr(
        home_dependencies,
        "settings",
        SimpleNamespace(app_env="development", dev_auth_enabled=True),
    )

    response = client.get("/api/rooms", headers={"X-Dev-User-Id": "1"})

    assert response.status_code == 200


def test_dev_auth_header_is_ignored_outside_development(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides.pop(get_current_user_id)
    monkeypatch.setattr(
        home_dependencies,
        "settings",
        SimpleNamespace(app_env="production", dev_auth_enabled=True),
    )

    response = client.get("/api/rooms", headers={"X-Dev-User-Id": "1"})

    assert response.status_code == 401


def test_unknown_route_returns_standard_not_found_response(client: TestClient) -> None:
    response = client.get("/api/unknown")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "NOT_FOUND",
            "message": "요청한 경로를 찾을 수 없습니다.",
        },
    }


def test_openapi_documents_normalized_validation_status() -> None:
    schema = app.openapi()

    responses = schema["paths"]["/api/rooms"]["post"]["responses"]
    assert "201" in responses
    assert "400" in responses
    assert "422" not in responses

    invite_lookup_responses = schema["paths"][
        "/api/rooms/invite/{invite_code}"
    ]["get"]["responses"]
    assert "401" not in invite_lookup_responses

    join_responses = schema["paths"][
        "/api/rooms/invite/{invite_code}/join"
    ]["post"]["responses"]
    assert {"200", "201", "409"} <= set(join_responses)


def test_unhandled_error_returns_standard_internal_error(client: TestClient) -> None:
    db_override = app.dependency_overrides[get_db]

    def fail_get_db():
        raise RuntimeError("internal details")

    app.dependency_overrides[get_db] = fail_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/api/rooms")
    finally:
        app.dependency_overrides[get_db] = db_override

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "서버 오류가 발생했습니다.",
        },
    }
