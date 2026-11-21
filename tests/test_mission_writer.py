"""미션 문구 생성 테스트. 실제 OpenAI API는 호출하지 않고 가짜 클라이언트를 씁니다."""
import json
from types import SimpleNamespace

from pydantic import SecretStr

from app.core.config import settings
from app.services import mission_writer
from app.services.mission_writer import write_missions

NAMES = ["클라이밍", "보드게임 카페", "맛집 투어"]


class FakeClient:
    """client.chat.completions.create(...) 만 흉내 냅니다."""

    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._content = content
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_returns_missions_in_same_order() -> None:
    client = FakeClient(json.dumps(["다 같이 클라이밍 완등", "보드게임 3연승 하기", "숨은 맛집 도장깨기"], ensure_ascii=False))
    assert write_missions(NAMES, client=client) == ["다 같이 클라이밍 완등", "보드게임 3연승 하기", "숨은 맛집 도장깨기"]


def test_request_shape(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_model", "gpt-test-model")
    client = FakeClient(json.dumps(["a", "b", "c"]))
    write_missions(NAMES, client=client)

    call = client.calls[0]
    assert call["model"] == "gpt-test-model"
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1] == {"role": "user", "content": "활동 3개:\n1. 클라이밍\n2. 보드게임 카페\n3. 맛집 투어"}


def test_code_block_wrapped_json_is_ok() -> None:
    client = FakeClient('```json\n["클라이밍 완등", "보드게임 3연승", "맛집 도장깨기"]\n```')
    assert write_missions(NAMES, client=client) == ["클라이밍 완등", "보드게임 3연승", "맛집 도장깨기"]


def test_invalid_item_falls_back_per_cell() -> None:
    client = FakeClient(json.dumps(["  다 같이\n클라이밍  완등 ", "가" * 15, ""], ensure_ascii=False))
    # 공백 정리 후 사용 / 14자 초과 → 활동 이름 / 빈 문자열 → 활동 이름
    assert write_missions(NAMES, client=client) == ["다 같이 클라이밍 완등", "보드게임 카페", "맛집 투어"]


def test_14_chars_is_allowed() -> None:
    fourteen = "가" * 14
    client = FakeClient(json.dumps([fourteen, "b", "c"], ensure_ascii=False))
    assert write_missions(NAMES, client=client)[0] == fourteen


def test_wrong_count_falls_back_all() -> None:
    client = FakeClient(json.dumps(["하나", "둘"], ensure_ascii=False))
    assert write_missions(NAMES, client=client) == NAMES


def test_not_json_falls_back_all() -> None:
    client = FakeClient("미션: 클라이밍 완등, 보드게임 3연승, 맛집 도장깨기")
    assert write_missions(NAMES, client=client) == NAMES


def test_json_object_instead_of_array_falls_back_all() -> None:
    client = FakeClient(json.dumps({"missions": ["a", "b", "c"]}))
    assert write_missions(NAMES, client=client) == NAMES


def test_api_error_falls_back_all() -> None:
    client = FakeClient(error=TimeoutError("8초 초과"))
    assert write_missions(NAMES, client=client) == NAMES


def test_no_api_key_skips_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(mission_writer, "_get_client", lambda key: (_ for _ in ()).throw(AssertionError("AI 호출하면 안 됨")))
    assert write_missions(NAMES) == NAMES


def test_empty_input() -> None:
    client = FakeClient("[]")
    assert write_missions([], client=client) == []
    assert client.calls == []
