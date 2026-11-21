"""환경변수 설정. 프로젝트 루트의 .env 파일도 읽습니다."""
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://gachi:gachi1234@localhost:3306/gachi?charset=utf8mb8"
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    frontend_base_url: str = "https://kankan-bingo.vercel.app"
    show_sql: bool = False

    kakao_rest_api_key: SecretStr = SecretStr("")
    kakao_client_secret: SecretStr = SecretStr("")
    kakao_redirect_uri: str = "http://localhost:8080/api/auth/kakao/callback"
    frontend_auth_success_url: str = "http://localhost:3000/auth/callback"

    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, gt=0)
    auth_cookie_secure: bool = False
    app_env: str = "production"
    dev_auth_enabled: bool = False

    # 인증 사진 저장소. S3_BUCKET이 비어 있으면 로컬 UPLOAD_DIR에 저장하고 /uploads 로 제공합니다.
    s3_bucket: str = ""
    aws_region: str = "ap-northeast-2"
    upload_dir: str = "uploads"

    # 빙고 미션 문구 AI. 키가 비어 있으면 활동 이름을 그대로 씁니다.
    # .env에서 OPENAI_API_KEY 와 OPENAI-API-KEY 둘 다 읽음
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI-API-KEY", "openai_api_key"),
    )
    openai_model: str = "gpt-5.6-luna"
    mission_ai_timeout_seconds: float = 8.0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
