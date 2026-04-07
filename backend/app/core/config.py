from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "fitbit-dify-app"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"

    dify_base_url: str = "https://api.dify.ai/v1"
    dify_api_key: str = ""
    dify_workflow_endpoint: str = "/workflows/run"
    dify_response_mode: str = "blocking"

    model_artifact_path: str = "./data/artifacts/fatigue_v1.json"

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        sqlite_prefix = "sqlite:///"
        if not self.database_url.startswith(sqlite_prefix):
            return self.database_url

        raw_path = self.database_url.removeprefix(sqlite_prefix)
        candidate = Path(raw_path)
        if candidate.is_absolute() or candidate.anchor:
            return self.database_url
        return f"sqlite:///{(BACKEND_DIR / candidate).resolve().as_posix()}"

    @property
    def resolved_model_artifact_path(self) -> Path:
        path = Path(self.model_artifact_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
