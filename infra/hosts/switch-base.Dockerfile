# Switch Base Image — M4 phase 02.
#
# A switch in M4 is a no-op container. Its only purpose is to give
# each wire's bridge a "named" port on the switch side so the user
# can `docker exec` into it and run `ip link` to debug. The actual
# L2 forwarding happens on the Linux bridge the backend creates
# (one bridge per wire), so a real learning switch is intentionally
# not implemented in v1 (see phases/milestone-4/overview.md and
# architecture.md §17 for the cut).
#
# Image contract:
#   * Installs: iproute2, bash
#   * No agent, no process
#   * Entrypoint: `sleep infinity`
#
# When the backend spawns a switch container, it attaches one veth
# per wired interface to the switch (one veth per wire the user
# drew from the switch). The other end of each veth is attached
# to the wire's bridge.

FROM alpine:3.19

RUN apk add --no-cache \
        iproute2 \
        bash

# No agent. No process. The container exists only as a debuggable
# namespace + a place to anchor veths.
ENTRYPOINT ["sleep", "infinity"]
