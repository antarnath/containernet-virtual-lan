"""Centralized configuration for the Host Agent.

Reads identity from environment variables set by per-host Dockerfiles
(HOST_ID, HOST_NAME, HOST_IP). Also defines ports and timing constants.
"""

import os


class Config:
    # Identity — set by per-host Dockerfile
    HOST_ID: str = os.getenv("HOST_ID", "unknown")
    HOST_NAME: str = os.getenv("HOST_NAME", "Unknown")
    HOST_IP: str = os.getenv("HOST_IP", "127.0.0.1")

    # Backend — not up yet in Phase 02, but the slot is reserved for Phase 03+
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://backend:8000")

    # Exposed ports
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9100"))
    MESSAGE_PORT: int = int(os.getenv("MESSAGE_PORT", "8080"))

    # Timing
    HEARTBEAT_INTERVAL_SEC: int = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "5"))


config = Config()