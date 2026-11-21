"""빙고 칸 미션 문구 생성 (OpenAI).

빙고판을 만들 때 고른 활동 9개를 한 번의 AI 호출로 보내 짧은 미션 문구로 바꿉니다.
예) 클라이밍 → 다 같이 클라이밍 완등

AI는 부가 기능이라 빙고판 생성을 막으면 안 됩니다.
- 키가 없으면 AI를 부르지 않고 활동 이름을 그대로 씁니다.
- 호출 실패 · 타임아웃(8초) · JSON이 아님 · 개수가 다름 → 9칸 모두 활동 이름
- 칸별로 14자를 넘거나 비어 있으면 → 그 칸만 활동 이름
"""
import json
import logging

from app.core.config import settings

log = logging.getLogger(__name__)

MAX_MISSION_LENGTH = 14

SYSTEM_PROMPT = """너는 친구들이 퇴근 후 함께 하는 '빙고 챌린지' 앱의 미션 작가야.
활동 목록을 받으면 각 활동을 빙고 칸에 들어갈 짧은 미션 문구로 바꿔.

규칙:
- 한국어, 공백 포함 14자 이내.
- 원래 활동이 무엇인지 바로 알 수 있게 핵심 단어를 남겨.
- 사진 한 장으로 인증할 수 있는 구체적인 행동으로 만들어. (예: 보드게임 카페 → 보드게임 3연승 하기)
- 위험하거나, 돈이 많이 들거나, 다른 사람에게 피해를 주는 미션은 만들지 마.
- 받은 활동과 같은 개수, 같은 순서로 답해.
- 설명 없이 JSON 문자열 배열만 출력해. 예: ["다 같이 클라이밍 완등", "보드게임 3연승 하기"]"""

_client = None


def _get_client(api_key: str):
    global _client
    if _client is None:
        from openai import OpenAI

        # 빙고판 생성 응답이 늦어지지 않도록 타임아웃 8초, 재시도 없음
        _client = OpenAI(api_key=api_key, timeout=settings.mission_ai_timeout_seconds, max_retries=0)
    return _client


def write_missions(activity_names: list[str], client=None) -> list[str]:
    """활동 이름 목록 → 같은 개수·같은 순서의 미션 문구 목록. 실패한 칸은 활동 이름 그대로."""
    names = list(activity_names)
    if not names:
        return []
    if client is None:
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            return names
        client = _get_client(api_key)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(names)},
            ],
        )
        missions = _parse_array(response.choices[0].message.content or "", len(names))
    except Exception:
        log.exception("미션 문구 생성 실패 → 활동 이름으로 대체")
        return names

    result = [_clean(m) or name for m, name in zip(missions, names)]
    replaced = sum(1 for m, name in zip(missions, names) if not _clean(m))
    if replaced:
        log.warning("미션 문구 %d개가 비어 있거나 %d자를 넘어 활동 이름으로 대체", replaced, MAX_MISSION_LENGTH)
    return result


def _user_prompt(names: list[str]) -> str:
    lines = "\n".join(f"{i}. {name}" for i, name in enumerate(names, start=1))
    return f"활동 {len(names)}개:\n{lines}"


def _parse_array(content: str, expected: int) -> list:
    """AI 응답에서 JSON 배열을 꺼냅니다. 코드블록(```json)으로 감싸 와도 처리합니다."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    data = json.loads(text)
    if not isinstance(data, list) or len(data) != expected:
        raise ValueError(f"미션 문구 개수가 다릅니다: 기대 {expected}, 실제 {len(data) if isinstance(data, list) else type(data).__name__}")
    return data


def _clean(mission) -> str | None:
    """공백 정리 후 1~14자면 사용, 아니면 None."""
    if not isinstance(mission, str):
        return None
    text = " ".join(mission.split())
    return text if 0 < len(text) <= MAX_MISSION_LENGTH else None
