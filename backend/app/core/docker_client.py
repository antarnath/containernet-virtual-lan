"""Docker SDK singleton.

Provides a single, lazily-initialized Docker client for the entire backend.
The client talks to whichever Docker daemon the `DOCKER_HOST` environment
variable points at:

    - unix:///var/run/docker.sock  (local socket; dev with mounted socket)
    - tcp://docker-proxy:2375      (production; via socket-proxy)

This module exposes two helpers:

    get_docker_client()  → docker.DockerClient   (the actual SDK object)
    ping()               → bool                  (is the daemon reachable?)

Keep this module tiny on purpose — anything more than a connection wrapper
belongs in container_service.py.
"""

from __future__ import annotations

import docker
from docker.errors import DockerException

from app.core.config import settings


# Lazily-initialized singleton. Created on first call to get_docker_client().
_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    """Return the shared Docker client, creating it on first use.

    Subsequent calls return the same instance — the Docker SDK is thread-safe
    and reuses its connection pool internally.
    """
    global _client
    if _client is None:
        # base_url wins if set explicitly; otherwise docker.from_env() reads
        # DOCKER_HOST from the environment. We pass base_url to be deterministic
        # against the value we stored in settings.
        _client = docker.DockerClient(base_url=settings.DOCKER_HOST)
    return _client


def ping() -> bool:
    """Return True if the Docker daemon responds to a ping, False otherwise.

    Used at startup to log whether orchestration is available, and by the
    /api/admin/docker/ping endpoint so a developer can verify connectivity.
    """
    try:
        get_docker_client().ping()
        return True
    except DockerException:
        return False
    except Exception:
        # Any other error (e.g., the socket file simply doesn't exist) is
        # treated the same: the daemon is unreachable from our vantage point.
        return False


def reset_client_for_tests() -> None:
    """Drop the cached client. Tests use this between cases to pick up
    environment changes (e.g., a different DOCKER_HOST)."""
    global _client
    _client = None
