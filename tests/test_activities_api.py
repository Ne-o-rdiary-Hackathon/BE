from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.home_dependencies import get_current_user_id
from app.db.session import get_db
from app.main import app


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE rooms ("
            "room_id INTEGER PRIMARY KEY, status VARCHAR(20) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE room_members ("
            "room_member_id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE activity_categories ("
            "category_id INTEGER PRIMARY KEY, parent_id INTEGER, "
            "category_name VARCHAR(50) NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE activities ("
            "activity_id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL, "
            "activity_name VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE user_responses ("
            "response_id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL, submitted_at DATETIME, "
            "created_at DATETIME NOT NULL, updated_at DATETIME, "
            "UNIQUE (room_id, user_id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE user_response_activities ("
            "response_activity_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "response_id INTEGER NOT NULL, activity_id INTEGER NOT NULL, "
            "selection_type VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, "
            "UNIQUE (response_id, activity_id))"
        )
        connection.exec_driver_sql(
            "INSERT INTO rooms VALUES "
            "(1, 'RECRUITING'), (2, 'RECRUITING'), (3, 'IN_PROGRESS')"
        )
        connection.exec_driver_sql(
            "INSERT INTO room_members VALUES "
            "(1, 1, 1), (2, 1, 2), (3, 2, 2), (4, 3, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO activity_categories VALUES "
            "(1, NULL, '스포츠', 1), (2, 1, '실내 스포츠', 1), "
            "(3, 1, '야외 스포츠', 1), (4, NULL, '비활성 카테고리', 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO activities VALUES "
            "(1, 2, '볼링', 1), (2, 2, '탁구', 1), "
            "(3, 3, '자전거 타기', 1), (4, 3, '비활성 활동', 0)"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def client(database_engine: Engine) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with Session(database_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: 1
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_activities_returns_active_category_hierarchy(client: TestClient) -> None:
    response = client.get("/api/v1/activities")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "categories": [
                {
                    "category_id": 1,
                    "category_name": "스포츠",
                    "subcategories": [
                        {
                            "category_id": 2,
                            "category_name": "실내 스포츠",
                            "activities": [
                                {"activity_id": 1, "activity_name": "볼링"},
                                {"activity_id": 2, "activity_name": "탁구"},
                            ],
                        },
                        {
                            "category_id": 3,
                            "category_name": "야외 스포츠",
                            "activities": [
                                {"activity_id": 3, "activity_name": "자전거 타기"}
                            ],
                        },
                    ],
                }
            ]
        },
        "error": None,
    }


def test_submit_activity_response_persists_selections_and_waits_for_members(
    client: TestClient, database_engine
) -> None:
    response = client.post(
        "/api/v1/rooms/1/responses/me/submit",
        json={"desired_activity_ids": [1, 2], "bored_activity_ids": [3]},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "SUBMITTED",
        "all_members_submitted": False,
    }

    with Session(database_engine) as db:
        saved = db.execute(
            text(
                "SELECT activity_id, selection_type FROM user_response_activities "
                "ORDER BY activity_id"
            )
        ).all()
    assert saved == [(1, "DESIRED"), (2, "DESIRED"), (3, "BORED")]


def test_submit_activity_response_reports_all_members_and_replaces_previous_choices(
    client: TestClient, database_engine
) -> None:
    client.post(
        "/api/v1/rooms/1/responses/me/submit",
        json={"desired_activity_ids": [1], "bored_activity_ids": [2]},
    )
    resubmitted = client.post(
        "/api/v1/rooms/1/responses/me/submit",
        json={"desired_activity_ids": [3], "bored_activity_ids": []},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["data"]["all_members_submitted"] is False

    with Session(database_engine) as db:
        saved = db.execute(
            text(
                "SELECT selected.activity_id, selected.selection_type "
                "FROM user_response_activities AS selected "
                "JOIN user_responses AS response "
                "ON response.response_id = selected.response_id "
                "WHERE response.user_id = 1"
            )
        ).all()
    assert saved == [(3, "DESIRED")]

    app.dependency_overrides[get_current_user_id] = lambda: 2
    response = client.post(
        "/api/v1/rooms/1/responses/me/submit",
        json={"desired_activity_ids": [], "bored_activity_ids": []},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "SUBMITTED",
        "all_members_submitted": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"desired_activity_ids": [1, 1], "bored_activity_ids": []},
        {"desired_activity_ids": [1], "bored_activity_ids": [1]},
        {"desired_activity_ids": [999], "bored_activity_ids": []},
        {"desired_activity_ids": [4], "bored_activity_ids": []},
    ],
)
def test_submit_activity_response_rejects_invalid_selections(
    client: TestClient, payload: dict[str, list[int]]
) -> None:
    response = client.post("/api/v1/rooms/1/responses/me/submit", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_submit_activity_response_rejects_non_members_and_missing_rooms(
    client: TestClient,
) -> None:
    payload = {"desired_activity_ids": [], "bored_activity_ids": []}
    forbidden = client.post("/api/v1/rooms/2/responses/me/submit", json=payload)
    missing = client.post("/api/v1/rooms/999/responses/me/submit", json=payload)

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ROOM_NOT_FOUND"


def test_submit_activity_response_rejects_non_recruiting_room(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/rooms/3/responses/me/submit",
        json={"desired_activity_ids": [], "bored_activity_ids": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROOM_NOT_RECRUITING"


def test_submit_activity_response_requires_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(get_current_user_id)

    response = client.post(
        "/api/v1/rooms/1/responses/me/submit",
        json={"desired_activity_ids": [], "bored_activity_ids": []},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ACCESS_TOKEN"


def test_openapi_documents_activity_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/activities" in paths
    assert "/api/v1/rooms/{roomId}/responses/me/submit" in paths
