import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./test.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "super-secret-jwt-key-with-at-least-32-chars")
    mail_server: str = os.getenv("MAIL_SERVER", "smtp.mailtrap.io")
    mail_port: int = int(os.getenv("MAIL_PORT", 2525))
    mail_username: str = os.getenv("MAIL_USERNAME", "user")
    mail_password: str = os.getenv("MAIL_PASSWORD", "password")
    mail_use_tls: bool = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    mail_use_ssl: bool = os.getenv("MAIL_USE_SSL", "False").lower() == "true"
    mail_default_sender: str = os.getenv("MAIL_DEFAULT_SENDER", "noreply@finmind.com")
    schedule_jobs: bool = os.getenv("SCHEDULE_JOBS", "False").lower() == "true"

    class Config:
        env_file = ".env"

