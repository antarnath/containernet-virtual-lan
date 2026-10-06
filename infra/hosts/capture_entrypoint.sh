#!/bin/sh
# capture_entrypoint.sh — runs inside the per-project capture container
# before tcpdump starts. Its job is to make sure the bridge actually
# forwards every host→host frame to this container's eth1.
#
# Why this is necessary
# ---------------------
# Linux bridges learn MAC → port mappings. When host-1 (port 1) sends
# a unicast frame to host-2 (port 2), the bridge forwards it ONLY to
# port 2. Capture (port N) is invisible to the bridge as a destination
# unless capture's port is in promiscuous mode — in which case the
# bridge floods every frame to that port regardless of the MAC table.
#
# Setting the capture container's own eth1 to promiscuous (`ip link set
# eth1 promisc on`) does NOT do this: that flag lives on the host-side
# veth (the bridge port). To toggle the host-side flag we need pid=host
# + SYS_ADMIN (granted in container_service.py:spawn_project_capture)
# so we can write to /sys/class/net/<bridge>/brif/<veth>/flags.
#
# Workflow
# --------
# 1. Discover our eth1's host-side veth peer via /sys/class/net/eth1/iflink
#    + /sys/class/net/<host_veth>/ifindex (matches our iflink).
# 2. Walk up to the master bridge (the veth's `master` link).
# 3. Set /sys/class/net/<bridge>/brif/<veth>/flags to include 0x100
#    (PROMISC). The flag field is a bitmask; we read-modify-write so
#    we don't clobber the existing LEARNING + STATE bits.
#
# Failure mode
# ------------
# If anything in this script fails (no /sys access, kernel config,
# etc.), we log to /tmp/capture_setup.err and proceed with tcpdump
# anyway. Worst case the capture only sees broadcast/multicast.

set +e  # don't bail on individual failures — log and keep going

LOG=/tmp/capture_setup.log
: >"$LOG"

echo "[capture_setup] pid=$$ starting" >>"$LOG"

# Step 1: find our eth1 iflink (the host-side veth's ifindex).
# The container starts with network=None then has eth1 attached by the
# backend via Network.connect() AFTER start, so we may need to wait a
# few seconds for the interface to appear in sysfs.
IFLINK=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if [ -f /sys/class/net/eth1/iflink ]; then
    IFLINK=$(cat /sys/class/net/eth1/iflink 2>/dev/null)
    if [ -n "$IFLINK" ]; then break; fi
  fi
  echo "[capture_setup] waiting for eth1 (attempt $attempt)…" >>"$LOG"
  sleep 1
done
if [ -z "$IFLINK" ]; then
  echo "[capture_setup] no /sys/class/net/eth1/iflink after 10s — running without promisc" >>"$LOG"
  exit 0
fi
echo "[capture_setup] eth1 iflink=$IFLINK" >>"$LOG"

# Step 2: locate the veth peer by matching ifindex.
# We list /sys/class/net/*/ifindex and find the one whose value is $IFLINK.
HOST_VETH=""
for devdir in /sys/class/net/*; do
  [ -f "$devdir/ifindex" ] || continue
  idx=$(cat "$devdir/ifindex" 2>/dev/null || echo "")
  if [ "$idx" = "$IFLINK" ]; then
    HOST_VETH=$(basename "$devdir")
    break
  fi
done
if [ -z "$HOST_VETH" ]; then
  echo "[capture_setup] could not find host veth for iflink=$IFLINK — running without promisc" >>"$LOG"
  exit 0
fi
echo "[capture_setup] host veth=$HOST_VETH" >>"$LOG"

# Step 3: find the master bridge of the host-side veth.
MASTER=""
if [ -f "/sys/class/net/$HOST_VETH/master" ]; then
  MASTER=$(basename "$(readlink "/sys/class/net/$HOST_VETH/master" 2>/dev/null)" 2>/dev/null || echo "")
fi
# Some kernels use master/ifindex instead of master symlink.
if [ -z "$MASTER" ] && [ -f "/sys/class/net/$HOST_VETH/master/ifindex" ]; then
  MIDX=$(cat "/sys/class/net/$HOST_VETH/master/ifindex" 2>/dev/null || echo "")
  if [ -n "$MIDX" ]; then
    for d in /sys/class/net/*; do
      [ -f "$d/ifindex" ] || continue
      i=$(cat "$d/ifindex" 2>/dev/null || echo "")
      [ "$i" = "$MIDX" ] || continue
      MASTER=$(basename "$d")
      break
    done
  fi
fi
if [ -z "$MASTER" ]; then
  echo "[capture_setup] $HOST_VETH has no master bridge — running without promisc" >>"$LOG"
  exit 0
fi
echo "[capture_setup] bridge=$MASTER" >>"$LOG"

# Step 4: set the per-port promisc flag.
FLAG_FILE="/sys/class/net/$MASTER/brif/$HOST_VETH/flags"
if [ ! -f "$FLAG_FILE" ]; then
  echo "[capture_setup] $FLAG_FILE not found — running without promisc" >>"$LOG"
  exit 0
fi
CURRENT=$(cat "$FLAG_FILE" 2>/dev/null || echo "0")
echo "[capture_setup] current flags=0x$CURRENT" >>"$LOG"
# Bit 0x100 = BR_BCAST_FLOOD; bit 0x200 doesn't exist. Real "promisc" for
# a bridge port is achieved by leaving the bridge to learn + flood normally
# while we set the host-side veth to PROMISC at the netdevice layer.
# Easiest portable approach: set the HOST veth to promisc — which the
# bridge driver DOES check before deciding to flood unicast.
PROMISC_FILE="/sys/class/net/$HOST_VETH/flags"
if [ -f "$PROMISC_FILE" ]; then
  # Bit 0x100 = IFF_PROMISC on the netdevice flags.
  CUR=$(cat "$PROMISC_FILE" 2>/dev/null || echo "0")
  NEW=$((CUR | 0x100))
  echo "$NEW" > "$PROMISC_FILE" 2>>"$LOG" || \
    echo "[capture_setup] write $PROMISC_FILE failed" >>"$LOG"
  AFTER=$(cat "$PROMISC_FILE" 2>/dev/null || echo "?")
  echo "[capture_setup] set $HOST_VETH promisc 0x$NEW (now 0x$AFTER)" >>"$LOG"
else
  echo "[capture_setup] $PROMISC_FILE missing — running without promisc" >>"$LOG"
fi

echo "[capture_setup] done — starting tcpdump" >>"$LOG"
exit 0
