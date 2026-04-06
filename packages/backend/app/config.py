from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.connectors import ConnectorType


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
    smtp_url: str | None = None  # e. g. smtp+ssl://user:pass@mail:465

    # Bank connector configuration
    default_connector: str = Field(default="mock")
    connector_api_keys: dict[str, str] = Field(default_factory=dict)

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_connector_type(self) -> ConnectorType:
        """Get the configured connector type."""
        try:
            return ConnectorType(self.default_connector.lower())
        except ValueError:
            return ConnectorType.MOCK
