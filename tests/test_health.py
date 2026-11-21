import asyncio
from unittest.mock import MagicMock, patch

import httpx

from app.main import app


def test_health_reports_server_and_database_up() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection

    with patch("app.api.health.engine.connect", return_value=connection):
        async def make_request():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                return await client.get("/api/health")

        response = asyncio.run(make_request())

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"server": "UP", "db": "UP"},
        "error": None,
    }
