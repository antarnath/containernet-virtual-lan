"""Smoke test for router_proxy against a running router.

Run inside the backend container with::

    python tests/test_router_proxy.py

Resolves the project's Router-1, asks the proxy for a fresh state,
and prints the result. Used to debug the BACKEND_NETWORK URL
selection when the agent isn't reachable on the docker0 bridge.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.core.docker_client import get_docker_client
from app.services import router_proxy
from app.services.router_proxy import _agent_url, get_router_state


def main() -> None:
    c = get_docker_client()
    # The Router-1 in the M4 acceptance project.
    containers = c.containers.list(
        all=True,
        filters={"label": "containernet.node=e2dcaadf-f269-491d-b0bb-c1322e6e68b1"},
    )
    print("found containers:", len(containers))
    if not containers:
        print("Router-1 is not running. Start the project first.")
        return
    cid = containers[0].id
    print("container id:", cid)
    print("agent url:", _agent_url(cid, "/state/all"))
    # Force a fresh fetch (no cache).
    router_proxy.invalidate("e2dcaadf-f269-491d-b0bb-c1322e6e68b1")
    import asyncio
    state = asyncio.run(
        get_router_state("e2dcaadf-f269-491d-b0bb-c1322e6e68b1", cid)
    )
    print("state.error:", state.error)
    print("state.routes (%d):" % len(state.routes))
    for r in state.routes:
        print(" ", r)
    print("state.neigh (%d):" % len(state.neigh))
    for n in state.neigh:
        print(" ", n)
    print("state.ifaces (%d):" % len(state.ifaces))
    for i in state.ifaces:
        print(" ", i)


if __name__ == "__main__":
    main()
