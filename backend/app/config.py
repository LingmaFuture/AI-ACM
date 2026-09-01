from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI-ACM"
    environment: str = "development"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite:///./aiacm.sqlite3"
    frontend_url: str = "http://localhost:3000"
    api_prefix: str = "/api/v1"

    redis_url: str = "redis://localhost:6379/0"
    sync_tasks: bool = True

    storage_backend: str = "local"
    local_storage_path: str = "./data/uploads"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "aiacm-private"

    ai_api_key: str | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-5-mini"

    smtp_url: str | None = None
    cookie_secure: bool = False
    upload_max_bytes: int = 20 * 1024 * 1024
    upload_max_pages: int = 200

    judge_mode: str = "local"
    judge_image: str = "aiacm-runner:latest"
    judge_workspace: str = "/tmp/aiacm-judge"
    judge_total_timeout_seconds: int = 20

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    @property
    def local_storage_dir(self) -> Path:
        return Path(self.local_storage_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

