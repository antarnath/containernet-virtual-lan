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

    # M4 phase 02 — the name of the backend's Docker network. Spawned
    # project nodes attach to this network in addition to their
    # per-wire bridges, so they can DNS-resolve ``backend`` for
    # heartbeats. The default is the docker-compose network name
    # (``<project_dir>_containernet_lan``); override via the
    # BACKEND_NETWORK env var if your compose project has a
    # different prefix (e.g. set to ``containernet_lan`` for a
    # compose project named ``default``).
    BACKEND_NETWORK: str = "containernet_containernet_lan"

    # M4 phase 02 — the URL host agents POST heartbeats to. Used as
    # the ``BACKEND_URL`` env var on every spawned host/server/attacker
    # container.
    BACKEND_URL: str = "http://backend:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()