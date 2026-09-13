"""Backend settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ContainerNet"
    API_V1_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/containernet"

    OFFLINE_THRESHOLD_SEC: int = 15

    # ─── Admin token (Phase 01) ──────────────────────────────────────────────
    # When empty (the default), /api/admin/* endpoints are disabled entirely.
    # Set this only in development via the .env file or docker-compose env.
    ADMIN_TOKEN: str = ""

    # ─── Docker orchestration (Phase 01) ──────────────────────────────────────
    # Where to reach the Docker daemon. Defaults to the local Unix socket
    # (works when /var/run/docker.sock is mounted). In production, set this
    # to a socket-proxy URL like tcp://docker-proxy:2375.
    DOCKER_HOST: str = "unix:///var/run/docker.sock"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()