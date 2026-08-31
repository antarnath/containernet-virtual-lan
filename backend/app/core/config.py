"""Backend settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ContainerNet"
    API_V1_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/containernet"

    OFFLINE_THRESHOLD_SEC: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()