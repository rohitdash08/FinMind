from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg2://finmind:finmind@postgres:5432/finmind"
    )
    redis_url: str = Field(default="redis://redis:6379/0")

    jwt_secret: str = Field(default="dev-secret-change")
    jwt_access_minutes: int = 15
    jwt_refresh_hours: int = 24

    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None

    email_from: str | None = None
    smtp_url: str | None = None  # e.g. smtp+ssl://user:pass@mail:465
    max_upload_bytes: int = 10 * 1024 * 1024
    cors_allowed_origins: str = Field(
        default=(
            "http://localhost:5173,"
            "http://127.0.0.1:5173,"
            "http://localhost:8081,"
            "http://127.0.0.1:8081,"
            "http://frontend,"
            "http://frontend:80"
        )
    )

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        return [origin for origin in origins if origin]
