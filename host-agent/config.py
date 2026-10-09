"""Centralized configuration for the Host Agent.

Reads identity from environment variables set by per-host Dockerfiles
(HOST_ID, HOST_NAME, HOST_IP). Also defines ports and timing constants.
"""

import os


class Config:
    # Identity — set by the backend's docker run when it spawns a project
    # host (or by a static-host Dockerfile for the legacy edition).
    HOST_ID: str = os.getenv("HOST_ID", "unknown")
    HOST_NAME: str = os.getenv("HOST_NAME", "Unknown")
    HOST_IP: str = os.getenv("HOST_IP", "127.0.0.1")

    # Project scope. None for legacy static pc1/pc2/pc3, a UUID for every
    # container the backend spawns.
    PROJECT_ID: str | None = os.getenv("PROJECT_ID") or None

    # Backend — reachable over the backend bridge. Defaults to the Docker
    # Compose service name; can be overridden via env for non-default
    # Compose projects.
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://backend:8000")

    # Exposed ports
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9100"))
    MESSAGE_PORT: int = int(os.getenv("MESSAGE_PORT", "8080"))
    # M4 phase 06 — attacker-only. The agent starts the attack control
    # server on this port only when AGENT_ROLE=attacker.
    ATTACK_CONTROL_PORT: int = int(os.getenv("ATTACK_CONTROL_PORT", "9092"))

    # Timing
    HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "5"))

    # M4 phase 06 — role + attack mode. Both default to None on a
    # non-attacker container. ATTACK_MODE is the *initial* mode the
    # container was spawned with; the user can override via the panel.
    AGENT_ROLE: str | None = os.getenv("AGENT_ROLE") or None
    ATTACK_MODE: str | None = os.getenv("ATTACK_MODE") or None


config = Config()