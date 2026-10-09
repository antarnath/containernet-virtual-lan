# Capture Base Image — one per project; captures every frame on the
# project's Linux bridge and emits one NDJSON object per packet.
# Used by the dashboard backend (M2-07 §2, M4 phase 04 per-link).
#
# Architecture note (M4-04)
# --------------------------
# A Linux bridge forwards host→host unicast frames directly between
# veth ports without ever delivering them to the bridge's own netns.
# tcpdump on the bridge interface therefore only sees broadcast,
# multicast, and bridge-local traffic — i.e. never the typical
# Host→Router ICMP/TCP/HTTP that the wire view is meant to show.
#
# The fix is a `tc` ingress→egress mirror on every bridge port that
# copies ingress frames to a dedicated veth in the host netns. The
# capture container (which runs with `network_mode=host`) then runs
# tcpdump on that veth and sees every frame that crosses the bridge.
# See infra/hosts/capture_run.sh for the implementation.
FROM alpine:3.19

# Runtime dependencies:
#   tcpdump          -> raw frame capture (CAP_NET_RAW is granted
#                       at run time via cap_add)
#   python3          -> runs the shim
#   iproute2         -> ip + tc; we need `tc` to install the ingress
#                       mirror that copies host→host frames to the
#                       capture veth. `iproute2-minimal` doesn't ship
#                       the `tc` binary, so we install the full one.
RUN apk add --no-cache \
        tcpdump \
        python3 \
        iproute2 \
        ebtables \
        bash

# Copy the capture shim into the image. Build context is the
# project root (set in docker-compose.yml), so host-agent/
# resolves correctly.
COPY host-agent/capture_shim.py /app/capture_shim.py
RUN chmod +x /app/capture_shim.py

# Helper script: wait until the project's bridge interface shows up
# in the host netns, then set up the capture veth + tc mirror and
# exec tcpdump. We sleep + retry because the bridge is created lazily
# by the backend's `Network.connect` call.
COPY infra/hosts/capture_run.sh /app/capture_run.sh
RUN chmod +x /app/capture_run.sh

WORKDIR /app

# Default command: wait for the bridge, then run tcpdump piped into
# the shim, writing NDJSON to $CAPTURE_FILE (a host-bind-mounted path).
#   tcpdump: -i <veth> capture on the mirror veth (not the bridge
#            itself; see capture_run.sh for why)
#            -U=buffered, -l=line buffered, -tttt=human timestamps,
#            -nn=no name/port resolution, -vvv=verbose, -w -=binary stdout
#   shim:    parses pcap, recomputes checksums, writes one JSON per line.
CMD ["/app/capture_run.sh"]
