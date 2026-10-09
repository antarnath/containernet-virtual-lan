#!/bin/bash
# capture_run.sh — entrypoint for the per-link capture container.
#
# Waits for the project's Linux bridge to show up in `ip link show`,
# then sets up a veth pair attached to the bridge (one end for tcpdump
# inside this container, the other end on the bridge), and installs
# `tc` ingress→egress mirror filters on every bridge port. Output
# (one NDJSON packet per line) is written to $CAPTURE_FILE.
#
# Why a veth + tc mirror (not tcpdump on the bridge directly)?
#   A Linux bridge forwards host→host unicast frames directly between
#   veth ports without ever delivering them to the bridge's own netns.
#   tcpdump on the bridge interface therefore only sees broadcast,
#   multicast, and bridge-local traffic — i.e. never the typical
#   Host→Router ICMP/TCP/HTTP that the wire view is meant to show.
#
#   The fix is a `tc` ingress→egress mirror on every bridge port that
#   copies ingress frames to a dedicated veth (`veth_cap0`) in the host
#   netns. The capture container (which runs with `network_mode=host`)
#   then runs tcpdump on `veth_cap0` and sees every frame that crosses
#   the bridge. Its peer `veth_cap1` is attached to the bridge so the
#   bridge can flood frames back to it as well (handy for the rare
#   unicast case the FDB hasn't learned yet).
#
# How we find the bridge:
#   Docker creates bridges with names derived from the network ID, not
#   the friendly user-supplied name (which lives at the network level).
#   So we accept either:
#     - $PROJECT_BRIDGE_NAME  (e.g. "c2203de07_d36f") — friendly
#     - $PROJECT_NETWORK_ID   (e.g. "a4a865c353d6")  — docker-internal
#   Then we probe each until we find an interface that exists.
set -u

OUT="${CAPTURE_FILE:-/tmp/capture.ndjson}"
ERR="${CAPTURE_FILE%.ndjson}.err"
BRIDGE_NAME="${PROJECT_BRIDGE_NAME:-}"
NET_ID="${PROJECT_NETWORK_ID:-}"

# Derive veth pair names. IFNAMSIZ is 15, so we keep things short.
# `vcap<id>_a` (inside the capture, where tcpdump runs) and
# `vcap<id>_b` (the bridge side).
if [ -n "$BRIDGE_NAME" ]; then
  SHORT="${BRIDGE_NAME:0:10}"
else
  SHORT="n${NET_ID:0:9}"
fi
CAP_A="vcap${SHORT:0:9}_a"
CAP_B="vcap${SHORT:0:9}_b"

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
echo "capture_run: bridge $BRIDGE ready, setting up capture veth $CAP_A/$CAP_B" >&2

# Ensure the bridge is in promiscuous mode (so AF_PACKET sockets see
# every frame even on a port that's flooded via the bridge FDB).
ip link set "$BRIDGE" promisc on >/dev/null 2>&1 || true

# ─── Create the capture veth pair and attach one end to the bridge ──
# We clean up any leftover veth from a previous run (e.g. container
# was restarted but the veth survived in the host's netns).
if ip link show "$CAP_A" >/dev/null 2>&1; then
  ip link del "$CAP_A" 2>/dev/null || true
fi
ip link add "$CAP_A" type veth peer name "$CAP_B" 2>>"$ERR" || {
  echo "capture_run: failed to create veth pair $CAP_A/$CAP_B" >&2
  exit 1
}
ip link set "$CAP_A" up promisc on 2>>"$ERR" || true
ip link set "$CAP_B" up 2>>"$ERR" || true
ip link set "$CAP_B" master "$BRIDGE" 2>>"$ERR" || {
  echo "capture_run: failed to attach $CAP_B to $BRIDGE" >&2
  ip link del "$CAP_A" 2>/dev/null || true
  exit 1
}

# ─── Install tc ingress→egress mirror on every existing port ────────
# For each bridge port other than $CAP_B, install an ingress qdisc +
# a u32 filter that mirrors incoming frames to $CAP_A.
#
# The `parent ffff:` ingress qdisc is the kernel's ingress hook.
# `action mirred egress mirror dev <veth>` copies the packet out the
# veth's egress path without dropping it from the original flow.
mirror_port() {
  local port="$1"
  if [ "$port" = "$CAP_A" ] || [ "$port" = "$CAP_B" ]; then return; fi
  if [ "$port" = "$BRIDGE" ]; then return; fi
  # Replace any existing filter from a previous run.
  tc qdisc del dev "$port" ingress 2>/dev/null || true
  tc qdisc add dev "$port" ingress 2>>"$ERR" || {
    echo "capture_run: tc qdisc add failed on $port" >&2
    return
  }
  tc filter add dev "$port" parent ffff: protocol all u32 match u8 0 0 \
    action mirred egress mirror dev "$CAP_A" 2>>"$ERR" || {
    echo "capture_run: tc filter add failed on $port" >&2
  }
}

# Install mirror on every current port of the bridge.
for port in $(ls /sys/class/net/"$BRIDGE"/brif/ 2>/dev/null); do
  mirror_port "$port"
done

# Watch for new ports (node containers that connect later) and install
# the mirror on them too. We poll the brif directory every 2s.
(
  while true; do
    sleep 2
    for port in $(ls /sys/class/net/"$BRIDGE"/brif/ 2>/dev/null); do
      if ! tc qdisc show dev "$port" ingress 2>/dev/null | grep -q ingress; then
        mirror_port "$port"
      fi
    done
  done
) &
MIRROR_WATCHER_PID=$!

# Make sure the watcher dies when we die.
trap 'kill $MIRROR_WATCHER_PID 2>/dev/null; ip link del "$CAP_A" 2>/dev/null; exit' INT TERM EXIT

# Export the resolved names so the shim/scripts can reference them.
export RESOLVED_BRIDGE="$BRIDGE"
export CAPTURE_IFACE="$CAP_A"

echo "capture_run: bridge=$BRIDGE tap=$CAP_A, starting tcpdump" >&2

# tcpdump runs on the capture veth end (in the host's netns). The
# mirror + the bridge flooding ensure we see every frame that crosses.
exec tcpdump -i "$CAP_A" -U -l -tttt -nn -vvv -w - 2>/dev/null \
  | python3 /app/capture_shim.py > "$OUT" 2> "$ERR"
