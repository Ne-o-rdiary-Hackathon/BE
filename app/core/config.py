"""환경변수 설정. 프로젝트 루트의 .env 파일도 읽습니다.
새 설정이 필요하면 Settings에 필드를 추가하고 아래 settings = ... 에서 읽어오세요."""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_allowed_origins: list[str]
    show_sql: bool


settings = Settings(
    database_url=_env("DATABASE_URL", "mysql+pymysql://gachi:gachi1234@localhost:3306/gachi?charset=utf8mb4"),
    cors_allowed_origins=[o.strip() for o in
                          _env("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
                          if o.strip()],
    show_sql=_env("SHOW_SQL", "false").strip().lower() in ("1", "true", "yes", "on"),
)
