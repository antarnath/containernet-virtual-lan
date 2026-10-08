"""Smoke test for the router_proxy parsers.

Run inside the backend container with::

    python tests/test_router_proxy_parser.py

The fixtures are the exact `ip` command outputs the router agent
returns. The parsers must handle the three real-world shapes:
  * `ip -j route` → JSON array
  * `ip neigh`     → plain text
  * `ip -br addr`  → plain text
"""

from __future__ import annotations

import sys

# Allow `python tests/test_router_proxy_parser.py` from the backend dir
sys.path.insert(0, "/app")

from app.services.router_proxy import _parse_ifaces, _parse_neigh, _parse_routes


ROUTES_TEXT = (
    "default via 172.17.0.1 dev eth0 \n"
    "10.0.0.0/24 dev eth1 proto kernel scope link src 10.0.0.1 \n"
    "172.17.0.0/16 dev eth0 proto kernel scope link src 172.17.0.2 \n"
)
NEIGH_TEXT = "10.10.0.3 dev eth2 lladdr 1e:13:13:4f:8c:6b DELAY \n"
IFACES_TEXT = (
    "lo               UNKNOWN        127.0.0.1/8 ::1/128 \n"
    "eth0@if124       UP             172.17.0.2/16 \n"
    "eth1@if125       UP             10.0.0.1/24 \n"
)


def main() -> None:
    routes = _parse_routes(ROUTES_TEXT)
    assert len(routes) == 3, f"expected 3 routes, got {len(routes)}"
    assert routes[0].destination == "default"
    assert routes[0].gateway == "172.17.0.1"
    assert routes[0].iface == "eth0"
    assert routes[1].destination == "10.0.0.0/24"
    assert routes[1].gateway == ""
    assert routes[1].protocol == "kernel"
    assert routes[1].scope == "link"
    assert routes[1].source == "10.0.0.1"

    neigh = _parse_neigh(NEIGH_TEXT)
    assert len(neigh) == 1
    assert neigh[0].ip == "10.10.0.3"
    assert neigh[0].iface == "eth2"
    assert neigh[0].mac == "1e:13:13:4f:8c:6b"
    assert neigh[0].state == "DELAY"

    ifaces = _parse_ifaces(IFACES_TEXT)
    assert len(ifaces) == 3
    assert ifaces[0].name == "lo"
    assert ifaces[0].ip_mask == "127.0.0.1/8"
    assert ifaces[1].name == "eth0@if124"
    assert ifaces[1].state == "UP"
    assert ifaces[1].ip_mask == "172.17.0.2/16"

    print("OK: routes=%d neigh=%d ifaces=%d" % (len(routes), len(neigh), len(ifaces)))


if __name__ == "__main__":
    main()
