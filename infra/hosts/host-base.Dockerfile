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
        bash \
        tcpdump

# Install the Host Agent's Python dependencies.
# These go in the base image so each per-host Dockerfile doesn't reinstall.
# --break-system-packages is required for Alpine's PEP 668 restriction.
# M4 phase 06 — scapy is needed by the attack engine (arp_spoof, etc).
# aiohttp is already a dep for the message service.
RUN pip3 install --no-cache-dir --break-system-packages \
        aiohttp \
        prometheus-client \
        scapy

# Default working directory
WORKDIR /app

# Copy the Host Agent source into the image. Build context is the project root
# (set in docker-compose.yml), so host-agent/ resolves correctly.
COPY host-agent /app/host-agent

# M4 phase 04 — per-link packet capture wrapper. The node spawn
# command sets NODE_CAPTURE_LINKS (one line per link this node
# participates in: "link_id iface capture_ndjson") and invokes
# this entrypoint, which starts a tcpdump per iface in the
# background before execing the agent command.
COPY infra/hosts/node_entrypoint.sh /app/node_entrypoint.sh
RUN chmod +x /app/node_entrypoint.sh

# Default command overridden in docker-compose.yml to run the agent.
CMD ["sleep", "infinity"]