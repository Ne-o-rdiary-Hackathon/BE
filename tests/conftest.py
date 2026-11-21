import pytest
from pydantic import SecretStr

from app.core.config import settings


@pytest.fixture(autouse=True)
def no_real_openai_calls(monkeypatch):
    """로컬 .env에 OpenAI 키가 있어도 테스트 중에는 실제 API를 부르지 않도록 키를 비웁니다.
    (AI 응답이 필요한 테스트는 가짜 클라이언트를 직접 넘깁니다.)"""
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
