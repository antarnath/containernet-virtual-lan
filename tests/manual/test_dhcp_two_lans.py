"""Test two DHCP Server interfaces on a SINGLE router.

dnsmasq binds one listening socket per ``interface=`` line at process
start. A SIGHUP re-reads the config text and re-applies ranges and
reservations, but it does NOT create a socket for an interface the
process didn't bind at startup.

So configuring a router's second interface with a Server used to
write /etc/dnsmasq.d/<iface2>.conf correctly and report success, while
dnsmasq kept serving only the first interface. Clients on the second
LAN sent well-formed DISCOVERs that were silently dropped — no OFFER,
no lease, host stuck on its .2 placeholder.

Every prior DHCP test missed this because each one gives a router at
most one Server interface: test_dhcp uses one, test_dhcp_relay puts
the server on one router and the relay on another. Two Servers on one
router is the most ordinary topology there is.

Run with:
    python3 tests/manual/test_dhcp_two_lans.py
"""
import ipaddress
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


print("Two DHCP Server interfaces on one router")
print("=" * 52)

pid = _req("POST", "/projects", {"name": "dhcp-two-lans"})[1]["id"]
print(f"  created project {pid}")

try:
    r1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]
    h2 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H2"})[1]
    print(f"  router + 2 hosts created")

    # Two interfaces on the SAME router, each feeding a different LAN.
    ri_a = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth0", "ip_address": "10.40.10.1",
                 "subnet_mask": "/24"})[1]
    ri_b = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth1", "ip_address": "10.40.20.1",
                 "subnet_mask": "/24"})[1]
    # Both hosts deliberately have no static IP — that is what makes
    # them DHCP clients.
    h1i = _req("POST", f"/projects/{pid}/nodes/{h1['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    h2i = _req("POST", f"/projects/{pid}/nodes/{h2['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_a["id"], "iface_b_id": h1i["id"]})
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_b["id"], "iface_b_id": h2i["id"]})
    print("  wired: R1.eth0↔H1 (10.40.10.0/24), R1.eth1↔H2 (10.40.20.0/24)")

    # Configure BOTH interfaces as Server. The order matters: the
    # first one starts dnsmasq, the second one is the case under
    # test.
    for iface, start, end in ((ri_a, "10.40.10.100", "10.40.10.200"),
                              (ri_b, "10.40.20.100", "10.40.20.200")):
        code, body = _req(
            "PUT",
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{iface['id']}/dhcp",
            {"enabled": True, "pool_start": start, "pool_end": end,
             "lease_time": 3600},
        )
        expect(f"Server on {iface['name']} → 200", code == 200,
               f"(got {code}: {body})")

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
    expect("project reached 'running'", status == "running",
           f"(got {status})")

    print("  waiting 15s for udhcpc on both hosts …")
    time.sleep(15)

    rid = docker("ps", "--filter", f"label=containernet.project={pid}",
                 "--filter", "label=containernet.role=router",
                 "--format", "{{.ID}}").stdout.strip()
    expect("router container running", bool(rid), f"(got {rid!r})")

    if rid:
        # The assertion that matters: dnsmasq must hold a socket for
        # BOTH LAN gateway addresses, not just the first.
        ns = docker("exec", rid, "netstat", "-ulnp").stdout
        has_a = "10.40.10.1:53" in ns
        has_b = "10.40.20.1:53" in ns
        expect("dnsmasq bound on LAN A gateway (10.40.10.1)",
               has_a, f"(netstat: {ns!r})")
        expect("dnsmasq bound on LAN B gateway (10.40.20.1)",
               has_b, f"(netstat: {ns!r})")

        leases = docker("exec", rid, "cat", "/var/lib/misc/dnsmasq.leases").stdout
        print(f"  leases:\n{leases}")
        lease_ips = []
        for line in leases.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                lease_ips.append(parts[2])
        expect("a lease exists on LAN A", any(
            ipaddress.ip_address(i) in ipaddress.ip_network("10.40.10.0/24")
            for i in lease_ips), f"(got {lease_ips})")
        expect("a lease exists on LAN B", any(
            ipaddress.ip_address(i) in ipaddress.ip_network("10.40.20.0/24")
            for i in lease_ips), f"(got {lease_ips})")

    # Client side: each host must hold an address from ITS OWN pool.
    hosts = docker("ps", "--filter", f"label=containernet.project={pid}",
                   "--filter", "label=containernet.role=host",
                   "--format", "{{.ID}}").stdout.split()
    expect("2 host containers running", len(hosts) == 2, f"(got {len(hosts)})")

    got_a, got_b = [], []
    for hcid in hosts:
        out = docker("exec", hcid, "ip", "-4", "-o", "addr", "show").stdout
        for line in out.splitlines():
            if " lo " in line:
                continue
            if "inet 10.40.10." in line:
                got_a.append(line.split()[3].split("/")[0])
            if "inet 10.40.20." in line:
                got_b.append(line.split()[3].split("/")[0])
    print(f"  LAN A host addrs: {got_a}\n  LAN B host addrs: {got_b}")

    # ".2" is the placeholder — proof the DISCOVER went unanswered.
    expect("LAN A host holds a pool address (not the .2 placeholder)",
           any(i != "10.40.10.2" for i in got_a), f"(got {got_a})")
    expect("LAN B host holds a pool address (not the .2 placeholder)",
           any(i != "10.40.20.2" for i in got_b), f"(got {got_b})")

    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\nTwo-LAN DHCP PASSED")
    else:
        print("\nTwo-LAN DHCP FAILED")
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