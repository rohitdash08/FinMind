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

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
