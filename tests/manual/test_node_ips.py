"""GET /api/projects/<pid>/node-ips — effective addressing for DHCP clients.

``project_interfaces.ip_address`` only ever holds what a human typed.
A host that leases from a router has NULL there, so every consumer that
resolves a node by its stored IP sees an empty string. The Send modal's
destination dropdown and route preview are the two that bite: with no
address to send to, the modal shows "Pick a source and destination"
and the Send button never enables, even though the host is up and has
a perfectly good lease.

This test pins the endpoint's contract:

  * a statically configured interface reports source="static"
  * a DHCP client reports its leased IP with source="dhcp"
  * an interface with neither reports ip=null, source=null — not "" and
    not a fabricated placeholder
  * the leased IP is one a route actually resolves, so the dropdown
    can offer a destination that works rather than one that dead-ends

Run with:
    python3 tests/manual/test_node_ips.py
"""
import json
import subprocess
import time
import urllib.error
import urllib.request as ur

BASE = "http://localhost:8000/api"

passed = 0
failed = 0


def _req(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = ur.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        resp = ur.urlopen(req, timeout=30)
        return resp.getcode(), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def expect(label, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  ✓ {label}")
        passed += 1
    else:
        print(f"  ✗ {label} {detail}")
        failed += 1


def docker(*args, timeout=25):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )


print("Effective node addresses (/node-ips)")
print("=" * 52)

pid = _req("POST", "/projects", {"name": "node-ips-test"})[1]["id"]
print(f"  created project {pid}")

try:
    r1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]
    h2 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H2"})[1]

    # Two LANs on one router, both DHCP servers — the router's own
    # interfaces are static, both hosts are clients.
    ri_a = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth0", "ip_address": "10.50.10.1",
                 "subnet_mask": "/24"})[1]
    ri_b = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth1", "ip_address": "10.50.20.1",
                 "subnet_mask": "/24"})[1]
    h1i = _req("POST", f"/projects/{pid}/nodes/{h1['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    h2i = _req("POST", f"/projects/{pid}/nodes/{h2['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_a["id"], "iface_b_id": h1i["id"]})
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_b["id"], "iface_b_id": h2i["id"]})

    for iface, start, end in ((ri_a, "10.50.10.100", "10.50.10.200"),
                              (ri_b, "10.50.20.100", "10.50.20.200")):
        _req("PUT",
             f"/projects/{pid}/nodes/{r1['id']}/interfaces/{iface['id']}/dhcp",
             {"enabled": True, "pool_start": start, "pool_end": end,
              "lease_time": 3600})

    # ─── static shape, before anything runs ──────────────────────
    #
    # Worth asserting on its own: an unconfigured client must come back
    # as null/null, never as "" (which the dropdown would render as an
    # empty option the user could still select) and never as a made-up
    # address.
    code, body = _req("GET", f"/projects/{pid}/node-ips")
    expect("GET /node-ips → 200", code == 200, f"(got {code}: {body})")
    expect("response echoes project_id", body.get("project_id") == pid,
           f"(got {body.get('project_id')!r})")

    nodes = body.get("nodes") or {}
    expect("every node present in the map",
           {r1["id"], h1["id"], h2["id"]} <= set(nodes),
           f"(got {sorted(nodes)})")

    r_ifs = nodes.get(r1["id"], [])
    expect("router eth0 reported as static",
           any(i["name"] == "eth0" and i["ip"] == "10.50.10.1"
               and i["source"] == "static" for i in r_ifs),
           f"(got {r_ifs})")
    expect("router eth1 reported as static",
           any(i["name"] == "eth1" and i["ip"] == "10.50.20.1"
               and i["source"] == "static" for i in r_ifs),
           f"(got {r_ifs})")

    h1_ifs = nodes.get(h1["id"], [])
    expect("unleased client reports ip=null",
           all(i["ip"] is None for i in h1_ifs), f"(got {h1_ifs})")
    expect("unleased client reports source=null",
           all(i["source"] is None for i in h1_ifs), f"(got {h1_ifs})")
    expect("unleased client carries no empty-string IP",
           all(i["ip"] != "" for i in h1_ifs), f"(got {h1_ifs})")

    # ─── start and lease ─────────────────────────────────────────
    print("  starting project…")
    code, _ = _req("POST", f"/projects/{pid}/start", None)
    expect("start accepted", code in (200, 202), f"(got {code})")

    deadline = time.time() + 120
    status = None
    while time.time() < deadline:
        status = _req("GET", f"/projects/{pid}")[1].get("status")
        if status == "running":
            break
        time.sleep(2)
    expect("project reached 'running'", status == "running", f"(got {status})")

    print("  waiting 20s for udhcpc on both hosts …")
    time.sleep(20)

    code, body = _req("GET", f"/projects/{pid}/node-ips")
    expect("GET /node-ips → 200 while running", code == 200, f"(got {code})")
    nodes = body.get("nodes") or {}

    h1_ips = [i["ip"] for i in nodes.get(h1["id"], []) if i["ip"]]
    h2_ips = [i["ip"] for i in nodes.get(h2["id"], []) if i["ip"]]
    print(f"  H1 leased: {h1_ips}\n  H2 leased: {h2_ips}")

    expect("H1 has a leased address", bool(h1_ips), f"(got {nodes.get(h1['id'])})")
    expect("H2 has a leased address", bool(h2_ips), f"(got {nodes.get(h2['id'])})")
    expect("H1 source is 'dhcp'",
           any(i["source"] == "dhcp" for i in nodes.get(h1["id"], [])),
           f"(got {nodes.get(h1['id'])})")
    expect("H2 source is 'dhcp'",
           any(i["source"] == "dhcp" for i in nodes.get(h2["id"], [])),
           f"(got {nodes.get(h2['id'])})")

    # The lease must come from the host's OWN pool, not the other
    # LAN's — a swapped lease is the failure mode where the dropdown
    # offers an address that routes nowhere.
    if h1_ips:
        expect("H1 leased from LAN A (10.50.10.0/24)",
               all(ip.startswith("10.50.10.") for ip in h1_ips), f"(got {h1_ips})")
    if h2_ips:
        expect("H2 leased from LAN B (10.50.20.0/24)",
               all(ip.startswith("10.50.20.") for ip in h2_ips), f"(got {h2_ips})")

    # ─── the address is actually routable ────────────────────────
    #
    # This is the whole point of the endpoint: the number it hands the
    # dropdown has to survive the route resolver. A leased IP that
    # resolve_route rejects would leave the modal permanently stuck on
    # "Unreachable" while the host is demonstrably up.
    if h1_ips and h2_ips:
        code, route = _req(
            "GET",
            f"/projects/{pid}/route?src={h1['id']}&dst={h2_ips[0]}",
        )
        print(f"  route H1 → H2 ({h2_ips[0]}): {json.dumps(route)[:300]}")
        # 422 is the "unreachable" answer — the exact case where a
        # leased IP is unusable as a dropdown destination.
        expect("cross-LAN route resolves", code == 200 and not route.get("error"),
               f"(got {code}: {route})")
        hops = (route or {}).get("hops") or []
        expect("route crosses the router (>=2 hops)", len(hops) >= 2,
               f"(got {len(hops)} hops)")
        # The hop list records nodes *traversed*, and the last entry
        # is the final forwarding node — the resolver never appends
        # the destination host itself. So assert on the path, not on
        # hops[-1] being H2.
        names = [hop.get("node_id") for hop in hops]
        expect("source is the first hop", bool(names) and names[0] == h1["id"],
               f"(got {names})")
        expect("router appears in the path", r1["id"] in names,
               f"(got {names})")
        # Both LANs' subnets must appear — that is what proves the
        # walk crossed from 10.50.10.0/24 to 10.50.20.0/24.
        subnets = {hop.get("link_subnet") for hop in hops if hop.get("link_subnet")}
        expect("path covers LAN A and LAN B",
               {"10.50.10.0/24", "10.50.20.0/24"} <= subnets,
               f"(got {subnets})")

    # ─── the leased destination is actually deliverable ──────────
    #
    # The route resolving is necessary but not sufficient: the send
    # path has to work out which *node* the destination IP belongs to
    # before it can hand the agent a target. That lookup reads the
    # same NULL ip_address column, so a leased destination used to be
    # undeliverable even with a good-looking route.
    if h1_ips and h2_ips:
        code, sent = _req("POST", f"/projects/{pid}/communications", {
            "src_node_id": h1["id"],
            "dst_node_id": None,
            "dst_ip": h2_ips[0],
            "protocol": "ICMP",
            "payload": "ping",
        })
        print(f"  send H1 → H2 ({h2_ips[0]}): {sent}")
        expect("send to a leased destination is accepted",
               code in (200, 202), f"(got {code}: {sent})")
        expect("send reports delivered",
               (sent or {}).get("status") == "delivered",
               f"(got {(sent or {}).get('status')}: "
               f"{(sent or {}).get('error')})")
        expect("send crossed both links",
               len((sent or {}).get("hops_crossed") or []) == 2,
               f"(got {(sent or {}).get('hops_crossed')})")

    # Cross-check against the container itself, so a stale lease table
    # or a stale cache cannot pass this test.
    hosts = docker("ps", "--filter", f"label=containernet.project={pid}",
                   "--filter", "label=containernet.role=host",
                   "--format", "{{.ID}}").stdout.split()
    expect("2 host containers running", len(hosts) == 2, f"(got {len(hosts)})")
    live = set()
    for hcid in hosts:
        out = docker("exec", hcid, "ip", "-4", "-o", "addr", "show").stdout
        for line in out.splitlines():
            if " lo " in line:
                continue
            live.add(line.split()[3].split("/")[0])
    print(f"  live container addresses: {sorted(live)}")
    if h1_ips:
        expect("H1 lease matches what the container actually holds",
               set(h1_ips) & live, f"(reported {h1_ips}, live {sorted(live)})")
    if h2_ips:
        expect("H2 lease matches what the container actually holds",
               set(h2_ips) & live, f"(reported {h2_ips}, live {sorted(live)})")

    # ─── 404 for an unknown project ──────────────────────────────
    code, _ = _req("GET", "/projects/00000000-0000-0000-0000-000000000000/node-ips")
    expect("unknown project → 404", code == 404, f"(got {code})")

    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\n/node-ips PASSED")
    else:
        print("\n/node-ips FAILED")
        raise SystemExit(1)
finally:
    try:
        _req("POST", f"/projects/{pid}/stop", None)
    except Exception:
        pass
    try:
        _req("DELETE", f"/projects/{pid}")
        print(f"  deleted project {pid}")
    except Exception as e:
        print(f"  cleanup error: {e}")