from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_server_and_database_up() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection

    with patch("app.api.health.engine.connect", return_value=connection):
        response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"server": "UP", "db": "UP"},
        "error": None,
    }
