#!/bin/bash
# capture_run.sh — entrypoint for the per-project capture container.
#
# Waits for the project's Linux bridge to show up in `ip link show`,
# then launches tcpdump on that interface piped through the shim into
# $CAPTURE_FILE (an NDJSON file the backend reads later).
#
# How we find the bridge:
#   Docker creates bridges with names derived from the network ID, not
#   the friendly user-supplied name (which lives at the network level).
#   So we accept either:
#     - $PROJECT_BRIDGE_NAME  (e.g. "proj_xxx_lan") — Docker-friendly name
#     - $PROJECT_NETWORK_ID   (e.g. "a4a865c353d6")  — Docker-internal name
#   Then we probe each until we find an interface that exists.
set -u

OUT="${CAPTURE_FILE:-/tmp/capture.ndjson}"
ERR="${CAPTURE_FILE%.ndjson}.err"
BRIDGE_NAME="${PROJECT_BRIDGE_NAME:-}"
NET_ID="${PROJECT_NETWORK_ID:-}"

mkdir -p "$(dirname "$OUT")" 2>/dev/null || true
mkdir -p "$(dirname "$ERR")" 2>/dev/null || true

echo "capture_run: waiting for bridge (name=$BRIDGE_NAME, netid=$NET_ID) (max 30s)..." >&2

BRIDGE=""
for i in $(seq 1 30); do
  if [ -n "$BRIDGE_NAME" ] && ip link show "$BRIDGE_NAME" >/dev/null 2>&1; then
    BRIDGE="$BRIDGE_NAME"
    break
  fi
  if [ -n "$NET_ID" ]; then
    CAND="br-${NET_ID}"
    CAND=${CAND:0:15}  # bridge names are limited to 15 chars by the kernel
    if ip link show "$CAND" >/dev/null 2>&1; then
      BRIDGE="$CAND"
      break
    fi
  fi
  sleep 1
done

if [ -z "$BRIDGE" ]; then
  echo "capture_run: bridge for $BRIDGE_NAME (netid=$NET_ID) never appeared" >&2
  exit 1
fi
echo "capture_run: bridge $BRIDGE ready, starting tcpdump" >&2

# Ensure the bridge itself is in promiscuous mode so the kernel does
# not filter out unicast frames destined to other MACs (the TCP case).
ip link set "$BRIDGE" promisc on >/dev/null 2>&1 || true

# Export the resolved bridge name so the shim/scripts can reference it.
export RESOLVED_BRIDGE="$BRIDGE"

exec tcpdump -i "$BRIDGE" -U -l -tttt -nn -vvv -w - 2>/dev/null \
  | python3 /app/capture_shim.py > "$OUT" 2> "$ERR"
