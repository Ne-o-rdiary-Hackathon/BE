"""환경변수 설정. 프로젝트 루트의 .env 파일도 읽습니다."""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://gachi:gachi1234@localhost:3306/gachi?charset=utf8mb8"
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
