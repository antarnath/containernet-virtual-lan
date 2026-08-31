# Host Base Image — shared foundation for every PC container.
# Based on Alpine Linux (small, fast, simple).
FROM alpine:3.19

# Install runtime dependencies:
#   python3, py3-pip     -> Host Agent
#   py3-psutil           -> CPU/RAM metrics
#   curl                 -> HTTP testing between hosts
#   iputils              -> Provides `ping`
#   busybox-extras       -> Extra networking tools
#   bash                 -> Better shell for debugging
RUN apk add --no-cache \
        python3 \
        py3-pip \
        py3-psutil \
        curl \
        iputils \
        busybox-extras \
        bash

# Install the Host Agent's Python dependencies.
# These go in the base image so each per-host Dockerfile doesn't reinstall.
# --break-system-packages is required for Alpine's PEP 668 restriction.
RUN pip3 install --no-cache-dir --break-system-packages \
        aiohttp \
        prometheus-client

# Default working directory
WORKDIR /app

# Default command overridden in docker-compose.yml to run the agent.
CMD ["sleep", "infinity"]