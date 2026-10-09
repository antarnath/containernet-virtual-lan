# Router Base Image — M4 phase 02.
#
# A router in M4 is a small Linux container with IP forwarding
# enabled and a tiny HTTP "router agent" on :9090 that the
# backend's router_proxy (phase 03) will poll. The router
# agent exposes the same commands as a real Cisco/Juniper
# router would, but backed by Linux's `ip` tool:
#
#   GET    /state/routes        -> `ip route` output (text)
#   GET    /state/neigh         -> `ip neigh` output (text)
#   GET    /state/ifaces        -> `ip -br addr` output (text)
#   GET    /state/all           -> JSON {routes, neigh, ifaces}
#   POST   /routes              -> add a static route
#                                  body: {"dst": "10.0.0.0/24",
#                                         "via": "10.10.0.1",
#                                         "dev": "eth0"}
#   DELETE /routes              -> remove a static route
#                                  body: {"dst": "...", "dev": "..."}
#   GET    /healthz             -> 200 if alive
#
# IP forwarding is enabled at boot via two redundant mechanisms
# (sysctl in entrypoint + --sysctl on `docker run`) because some
# Docker daemon versions ignore one of them.

FROM alpine:3.19

RUN apk add --no-cache \
        python3 \
        iproute2 \
        tcpdump \
        bash

# Router agent source — copied in at build time. The build context
# is the project root (set in docker-compose.yml), so the relative
# path `router-agent` resolves correctly.
COPY router-agent /app/router-agent

# M4 phase 04 — per-link packet capture wrapper. The node spawn
# command sets NODE_CAPTURE_LINKS (one line per link this node
# participates in: "link_id iface capture_ndjson") and invokes
# this entrypoint, which starts a tcpdump per iface in the
# background before execing the agent command.
# (The wrapper expects capture_shim.py under /app/host-agent — we
# copy that too so the router container can run it without an
# extra layer.)
COPY host-agent/capture_shim.py /app/host-agent/capture_shim.py
COPY infra/hosts/node_entrypoint.sh /app/node_entrypoint.sh
RUN chmod +x /app/node_entrypoint.sh

# Enable IP forwarding at the kernel level. This is a per-sysctl
# namespace, so it must be set in the entrypoint (the image-built
# /proc/sys/net/ipv4/ip_forward is the host's value, not ours).
# We also set it via `docker run --sysctl net.ipv4.ip_forward=1`
# in the backend as a belt-and-braces measure.
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo 'sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true' >> /entrypoint.sh && \
    echo 'exec /app/node_entrypoint.sh python3 /app/router-agent/agent.py' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
