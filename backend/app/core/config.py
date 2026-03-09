from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480

    # Database
    database_url: str = "postgresql+asyncpg://agile:agile@db:5432/agile_intel"
    database_url_sync: str = "postgresql://agile:agile@db:5432/agile_intel"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Anthropic
    anthropic_api_key: str = ""

    # Jira
    jira_client_id: str = ""
    jira_client_secret: str = ""
    jira_redirect_uri: str = "http://localhost:8000/api/v1/integrations/jira/callback"
    jira_service_email: str = ""
    jira_service_api_token: str = ""
    jira_cloud_id: str = ""
    jira_base_url: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # Google
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"

    # Pipeline schedules
    jira_sync_interval_minutes: int = 15
    slack_sync_interval_minutes: int = 30
    transcript_sync_interval_minutes: int = 60

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
