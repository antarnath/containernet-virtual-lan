#!/bin/sh
# node_entrypoint.sh — wraps the host/router agent with a per-link
# packet capture. Before execing the agent, it parses the
# NODE_CAPTURE_LINKS env var (a JSON-ish list of
#   link_id:iface:ndjson_path
# separated by newlines) and starts one background tcpdump per line,
# piping its pcap output through capture_shim into the link's NDJSON
# file.
#
# Why per-node instead of per-link sidecar container?
#   A Linux bridge's fast-forward path bypasses AF_PACKET, TC, and
#   netfilter for host→host unicast frames. tcpdump on the bridge
#   itself (or any tap attached to the bridge) only sees broadcast,
#   multicast, and bridge-local traffic — never Host→Router ICMP/TCP.
#   The only reliable way to capture wire-level traffic is from each
#   node's veth inside the node's own netns. A node's interface
#   receives (and transmits) every frame that crosses its link, so
#   the per-node capture sees the full wire.
#
# Multiple nodes on the same link write to the same NDJSON file
# concurrently. Each line is a single JSON object ≤ PIPE_BUF, so
# concurrent appends are safe.
#
# Why we don't `exec` the agent:
#   We tried `( tcpdump | shim ) & exec agent`, but Alpine's ash
#   reaps the subshell when the parent execs (the shell image is
#   replaced, the background pipe is closed, tcpdump gets EPIPE).
#   The fix: don't exec. Run the agent as a child, wait for it,
#   and re-parent the captures via `setsid` so they survive the
#   agent exiting. When the agent dies, we kill the captures and
#   the container exits cleanly.

# ── Start per-link packet captures ───────────────────────────────
# NODE_CAPTURE_LINKS format: one line per link, "link_id iface ndjson_path"
#
# IMPORTANT: we must NOT pipe the heredoc/var into `while read` —
# that creates a subshell, and the subshell's backgrounded
# children (our setsid'd captures) are reaped when the subshell
# exits. Instead we read the env var directly line by line.
# This was the root cause of "captures silently die" — the
# subshell from the pipe was exiting before tcpdump bound its
# AF_PACKET socket, and took the capture with it.
#
# ALSO IMPORTANT: we must NOT use `set -- $LINE` to parse the
# line — that overwrites the positional parameters ($@) that hold
# the agent command we want to exec after the captures start.
# We use a temp variable + explicit field reads instead.

# Save the original args (the agent command). We'll need them
# after the capture loop, which mangles $@ if we use set --.
ORIG_ARGS="$*"
# (We also need to preserve the empty-arg case — a one-element
# ORIG_ARGS would be hidden if the agent got no args, so we
# explicitly remember the count too.)
ORIG_ARGC=$#

# Give the network interfaces a moment to come up. The container
# is attached to multiple bridges by node_service._reattach_to_bridges
# and the order of operations means eth1 may not be UP when we
# first get here. If tcpdump races the interface up, it gets
# "ioctl: No such device" and dies — and the capture_shim
# inherits an empty stdin (→ "EOF before pcap header").
sleep 2

if [ -n "$NODE_CAPTURE_LINKS" ]; then
  NCL_LINES=$(echo "$NODE_CAPTURE_LINKS" | wc -l)
  NCL_IDX=0
  while [ "$NCL_IDX" -lt "$NCL_LINES" ]; do
    NCL_IDX=$((NCL_IDX + 1))
    LINE=$(echo "$NODE_CAPTURE_LINKS" | sed -n "${NCL_IDX}p")
    [ -z "$LINE" ] && continue
    # Parse with cut (no field splitting → no $@ clobber).
    LINK_ID=$(echo "$LINE" | cut -d' ' -f1)
    IFACE=$(echo "$LINE" | cut -d' ' -f2)
    NDJ=$(echo "$LINE" | cut -d' ' -f3-)
    [ -z "$LINK_ID" ] && continue
    if [ -z "$IFACE" ]; then
      echo "node_entrypoint: $LINK_ID has no iface, skipping capture" >&2
      continue
    fi
    if [ -z "$NDJ" ]; then
      echo "node_entrypoint: $LINK_ID has no capture file, skipping" >&2
      continue
    fi
    # Start the tcpdump in the background, in a new session, with
    # all I/O detached from the entrypoint. setsid puts it in its
    # own process group so it doesn't get SIGHUP when we exit.
    OUTDIR=$(dirname "$NDJ")
    mkdir -p "$OUTDIR" 2>/dev/null || true
    echo "node_entrypoint: capturing $IFACE → $NDJ (link=$LINK_ID)" >&2
    setsid sh -c "
      exec tcpdump -i '$IFACE' -U -l -tttt -nn -vvv -w - 2>/dev/null \
        | python3 /app/host-agent/capture_shim.py \
            >> '$NDJ' \
            2>>'${NDJ%.ndjson}.err'
    " </dev/null >/dev/null 2>&1 &
    CAPTURE_PID="$!"
    echo "node_entrypoint: capture subshell pid=$CAPTURE_PID link=$LINK_ID" >&2
  done
fi

# Give the captures a moment to bind their AF_PACKET sockets before
# we start the agent — otherwise tcpdump can race with interface
# up events and exit immediately.
sleep 1

# ── Run the original entrypoint (the agent) as a child ───────────
# We don't exec — the entrypoint script must outlive the agent
# process so its backgrounded captures stay alive. When the agent
# exits, we kill any remaining capture processes and exit.
echo "node_entrypoint: starting agent: $ORIG_ARGS" >&2
# Run the original args (preserved before the capture loop
# clobbered $@).
if [ "$ORIG_ARGC" -gt 0 ]; then
  # Reconstruct $@ from ORIG_ARGS (one arg per token).
  set -- $ORIG_ARGS
else
  set --
fi
"$@" &
AGENT_PID=$!
echo "node_entrypoint: agent pid=$AGENT_PID" >&2

# When the agent exits, clean up our background captures. We trap
# signals so docker stop propagates correctly.
cleanup() {
  echo "node_entrypoint: cleanup on exit" >&2
  # Kill the entire process group of any setsid'd subshells.
  for p in $(jobs -p); do
    kill -TERM -"$p" 2>/dev/null || true
  done
  # If the agent is still alive (signal handler), kill it.
  kill -TERM "$AGENT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for the agent. The script will be replaced when the agent
# exits (via the trap), but for the docker container this is
# exactly what we want: the container stays running as long as
# the agent is running.
wait "$AGENT_PID"
AGENT_EXIT=$?
echo "node_entrypoint: agent exited with code $AGENT_EXIT" >&2
exit "$AGENT_EXIT"
