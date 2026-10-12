#!/bin/sh
# udhcpc_placeholder.sh — custom udhcpc client script that preserves
# the placeholder IP on the interface if no lease is obtained.
#
# Busybox's default /usr/share/udhcpc/default.script does:
#   deconfig: ip addr flush dev $interface
#   bound:    ip addr add $ip/$mask dev $interface; route add default
#
# We change `deconfig` to be a no-op so the placeholder IP we set
# during spawn (in node_service._ensure_veth_ip) survives a failed
# DHCP exchange. Without this, udhcpc with `-n` (exit if no lease)
# flushes the placeholder on every retry cycle.
#
# The bound case still works normally — when a DHCP OFFER is
# accepted, the kernel adds the lease IP and the placeholder is
# replaced.

case "$1" in
  deconfig)
    # Don't flush — keep the placeholder.
    ;;
  renew)
    # udhcpc calls this on lease renew. Run the same logic as bound.
    ;;
  bound)
    if [ -n "$ip" ] && [ -n "$interface" ]; then
      # Remove the placeholder IP from the interface first so the
      # lease IP doesn't conflict on the same subnet.
      ip -4 addr flush dev "$interface" 2>/dev/null || true
      ip addr add "$ip/${mask:-24}" dev "$interface" || true
    fi
    if [ -n "$router" ] && [ -n "$interface" ]; then
      # Don't override the default route — node_entrypoint.sh
      # installs it explicitly from DEFAULT_GATEWAY_IP. udhcpc's
      # default script would add a default route per-router which
      # races the entrypoint's.
      :
    fi
    ;;
  leasefail)
    # No lease. Leave the placeholder in place.
    ;;
esac

exit 0
