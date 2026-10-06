# Capture Base Image — one per project; captures every frame on the
# project's Linux bridge and emits one NDJSON object per packet.
# Used by the dashboard backend (M2-07 §2).
#
# Architecture note (M2-07 §2.4)
# --------------------------------
# The capture container runs in the HOST network namespace with
# CAP_NET_RAW. It tcpdumps on the project's Linux bridge interface
# (e.g. `proj_3da0e38403a2_lan`). The Linux kernel delivers every
# frame received on a bridge interface to AF_PACKET sockets opened on
# it, so we see host→host unicast frames WITHOUT having to manipulate
# the bridge's per-port promiscuous flag (which we can't from outside
# the host anyway).
#
# Why not attach as a bridge port?
# A port-attached container would only see frames the bridge floods
# to its port — i.e. broadcast, multicast, and unknown unicast. Known
# unicast frames (the typical case for host→host TCP) would be
# forwarded only to the destination host's port, never to capture.
# Capturing the bridge itself sidesteps that limitation entirely.
FROM alpine:3.19

# Runtime dependencies:
#   tcpdump          -> raw frame capture (CAP_NET_RAW is granted
#                       at run time via cap_add)
#   python3          -> runs the shim
RUN apk add --no-cache \
        tcpdump \
        python3 \
        iproute2-minimal \
        bash

# Copy the capture shim into the image. Build context is the
# project root (set in docker-compose.yml), so host-agent/
# resolves correctly.
COPY host-agent/capture_shim.py /app/capture_shim.py
RUN chmod +x /app/capture_shim.py

# Helper script: wait until the project's bridge interface shows up
# in the host netns, then exec tcpdump on it. We sleep + retry because
# the bridge is created lazily by the backend's `Network.connect` call.
COPY infra/hosts/capture_run.sh /app/capture_run.sh
RUN chmod +x /app/capture_run.sh

WORKDIR /app

# Default command: wait for the bridge, then run tcpdump piped into
# the shim, writing NDJSON to $CAPTURE_FILE (a host-bind-mounted path).
#   tcpdump: -i <bridge> capture on the project bridge interface
#            -U=buffered, -l=line buffered, -tttt=human timestamps,
#            -nn=no name/port resolution, -vvv=verbose, -w -=binary stdout
#   shim:    parses pcap, recomputes checksums, writes one JSON per line.
CMD ["/app/capture_run.sh"]
