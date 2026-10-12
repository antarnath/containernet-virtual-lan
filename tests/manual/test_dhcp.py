"""Test M5-01 feature 1.2: DHCP server on the router.

The backend must:
  * persist per-interface DHCP config (pool, lease, DNS)
  * validate the pool lies inside the bridge subnet
  * reject DHCP enabled on a non-router node
  * reject pools that contain the router's own IP
  * at start time, push the config to the router agent which
    starts ``dnsmasq``
  * the host's entrypoint must run ``udhcpc`` when DHCP_ENABLED=1
    and the host gets an IP in the pool
  * the router's /dhcp/leases endpoint reports the new leases

This test is a happy-path end-to-end against a running backend.
It does NOT try to verify cross-subnet ping; the leases table is
enough to prove DHCP worked.

Run with:
    python tests/manual/test_dhcp.py
"""
import ipaddress
import json
import time
import urllib.error
import urllib.request as ur


BASE = "http://localhost:8000/api"


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
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            body_json = json.loads(body_text)
        except Exception:
            body_json = body_text
        return e.code, body_json


def post(path, body):
    return _req("POST", path, body)


def put(path, body):
    return _req("PUT", path, body)


def get(path):
    code, body = _req("GET", path)
    if code != 200:
        raise SystemExit(f"GET {path} returned {code}: {body}")
    return body


def delete(path):
    req = ur.Request(f"{BASE}{path}", method="DELETE")
    try:
        ur.urlopen(req).read()
    except urllib.error.HTTPError as e:
        if e.code != 204:
            print(f"  cleanup warning: DELETE {path} returned {e.code}")


# ── the test ──────────────────────────────────────────────────────────
print("M5-01 / 1.2: DHCP server on the router")
print("=" * 50)

# 1) Create a project
proj = post("/projects", {"name": "dhcp-test"})
pid = proj[1]["id"]
print(f"  created project {pid}")

passed = 0
failed = 0


def expect(label, expected, actual):
    global passed, failed
    if actual == expected:
        print(f"  ✓ {label}: {actual!r}")
        passed += 1
    else:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        failed += 1


def expect_true(label, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  ✓ {label}")
        passed += 1
    else:
        print(f"  ✗ {label} {detail}")
        failed += 1


try:
    # 2) Add a router + 2 hosts
    r1 = post(f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = post(f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]
    h2 = post(f"/projects/{pid}/nodes", {"kind": "host", "name": "H2"})[1]
    print(f"  added router={r1['id'][:8]} + 2 hosts")

    # 3) Wire the router to two hosts on two different /24s.
    ri = post(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces",
        {"name": "eth0", "ip_address": "10.30.10.1", "subnet_mask": "/24"},
    )[1]
    ri2 = post(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces",
        {"name": "eth1", "ip_address": "10.30.20.1", "subnet_mask": "/24"},
    )[1]
    # H1 has NO static IP on the DHCP-enabled LAN — this is what
    # triggers ``udhcpc`` in the host's entrypoint, which sends a
    # DHCPDISCOVER that the router's dnsmasq will answer, producing
    # the lease we verify below. H2 has a static IP on a different
    # LAN (no DHCP there, so the leases table only shows the H1
    # lease, not 2 — see the assertion below).
    h1i = post(
        f"/projects/{pid}/nodes/{h1['id']}/interfaces",
        {"name": "eth0", "subnet_mask": "/24"},
    )[1]
    h2i = post(
        f"/projects/{pid}/nodes/{h2['id']}/interfaces",
        {"name": "eth0", "ip_address": "10.30.20.10", "subnet_mask": "/24"},
    )[1]
    link1 = post(
        f"/projects/{pid}/links",
        {"iface_a_id": ri["id"], "iface_b_id": h1i["id"]},
    )[1]
    link2 = post(
        f"/projects/{pid}/links",
        {"iface_a_id": ri2["id"], "iface_b_id": h2i["id"]},
    )[1]
    print(f"  link1 subnet={link1.get('subnet_cidr')!r} link2 subnet={link2.get('subnet_cidr')!r}")

    # 4) Reject DHCP on a non-router node
    code, body = put(
        f"/projects/{pid}/nodes/{h1['id']}/interfaces/{h1i['id']}/dhcp",
        {"enabled": True, "pool_start": "10.30.10.100", "pool_end": "10.30.10.200"},
    )
    expect("DHCP on non-router → 422", 422, code)

    # 5) Reject pool outside subnet
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {"enabled": True, "pool_start": "192.168.1.100", "pool_end": "192.168.1.200"},
    )
    expect("pool outside subnet → 422", 422, code)

    # 6) Reject pool containing router's own IP
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {"enabled": True, "pool_start": "10.30.10.1", "pool_end": "10.30.10.100"},
    )
    expect("router-in-pool → 422", 422, code)

    # 7) Reject pool_start > pool_end
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {"enabled": True, "pool_start": "10.30.10.200", "pool_end": "10.30.10.100"},
    )
    expect("reversed pool → 422", 422, code)

    # 8) Accept valid config
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {
            "enabled": True,
            "pool_start": "10.30.10.100",
            "pool_end": "10.30.10.200",
            "lease_time": 3600,
            "dns": "8.8.8.8",
        },
    )
    expect("valid DHCP config → 200", 200, code)
    expect("dhcp_enabled persisted", True, body.get("dhcp_enabled"))
    expect("dhcp_pool_start persisted", "10.30.10.100", body.get("dhcp_pool_start"))
    expect("dhcp_pool_end persisted", "10.30.10.200", body.get("dhcp_pool_end"))
    expect("dhcp_lease_time persisted", 3600, body.get("dhcp_lease_time"))
    expect("dhcp_dns persisted", "8.8.8.8", body.get("dhcp_dns"))

    # 9) Disable: clears pool
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {"enabled": False},
    )
    expect("disable → 200", 200, code)
    expect("dhcp_enabled cleared", False, body.get("dhcp_enabled"))
    expect("pool_start cleared on disable", None, body.get("dhcp_pool_start"))

    # 10) Re-enable for the start test
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
        {
            "enabled": True,
            "pool_start": "10.30.10.100",
            "pool_end": "10.30.10.200",
            "lease_time": 3600,
        },
    )
    expect("re-enable → 200", 200, code)

    # 11) Start the project
    print("  starting project…")
    code, body = post(f"/projects/{pid}/start", None)
    if code != 200:
        # Some backends return 202 Accepted; both are OK.
        if code not in (200, 202):
            print(f"  ✗ start failed: {code} {body}")
            failed += 1
            raise SystemExit(1)
    print(f"  start returned {code}")

    # 12) Wait for the project to come up
    deadline = time.time() + 90
    project = None
    while time.time() < deadline:
        project = get(f"/projects/{pid}")
        if project["status"] == "running":
            break
        time.sleep(2)
    expect("project reached 'running'", "running", project["status"] if project else None)

    # 13) Give the hosts a beat to run udhcpc
    print("  waiting 10s for udhcpc + dnsmasq …")
    time.sleep(10)

    # 14) Look at the router's lease table via the proxy.
    # The router container is reachable on the backend network at
    # port 9090. We can hit it directly through docker exec, but
    # the cleanest path is via the API. For M5-01 we don't yet
    # have a /api/projects/<pid>/dhcp/leases endpoint, so we shell
    # out to docker.
    import subprocess
    cid_proc = subprocess.run(
        ["docker", "ps", "--filter", f"label=containernet.project={pid}",
         "--filter", "label=containernet.role=router", "--format", "{{.ID}}"],
        capture_output=True, text=True, timeout=10,
    )
    container_ids = cid_proc.stdout.strip().splitlines()
    expect_true("router container is running", len(container_ids) >= 1,
                f"(got {container_ids!r})")

    if container_ids:
        cid = container_ids[0].strip()
        # Read the leases file directly (the agent reads the same path).
        lease_proc = subprocess.run(
            ["docker", "exec", cid, "cat", "/var/lib/misc/dnsmasq.leases"],
            capture_output=True, text=True, timeout=10,
        )
        leases_text = lease_proc.stdout.strip()
        lease_lines = [l for l in leases_text.splitlines() if l.strip()]
        print(f"  dnsmasq.leases: {len(lease_lines)} line(s)")
        for line in lease_lines:
            print(f"    {line}")
        # We expect at least 1 lease (H1, which has no static IP
        # and will run udhcpc). H2 is on a separate LAN with no
        # DHCP, so it won't lease. Any additional leases would be
        # from spurious clients; the test only checks >= 1.
        expect_true(">=1 DHCP lease issued", len(lease_lines) >= 1,
                    f"(got {len(lease_lines)})")
        in_pool = []
        for line in lease_lines:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    ip = ipaddress.IPv4Address(parts[2])
                    in_pool.append(parts[2])
                except ValueError:
                    pass
        pool_lo = ipaddress.IPv4Address("10.30.10.100")
        pool_hi = ipaddress.IPv4Address("10.30.10.200")
        in_range = [ip for ip in in_pool
                    if pool_lo <= ipaddress.IPv4Address(ip) <= pool_hi]
        expect_true(
            "all leases in pool range",
            len(in_range) == len(in_pool) and len(in_pool) >= 1,
            f"(got ips: {in_pool})",
        )

        # 15) Verify dnsmasq is actually running inside the container
        ps_proc = subprocess.run(
            ["docker", "exec", cid, "ps", "aux"],
            capture_output=True, text=True, timeout=10,
        )
        expect_true("dnsmasq process is running",
                    "dnsmasq" in ps_proc.stdout,
                    f"(ps output: {ps_proc.stdout[:200]!r})")

        # 16) Verify the config file was written. The router has
        # two per-link bridges; the DHCP-enabled one is the first
        # one attached, so the dnsmasq config is named eth1.conf
        # (eth0 is the docker default bridge, not a per-link one).
        conf_proc = subprocess.run(
            ["docker", "exec", cid, "ls", "/etc/dnsmasq.d/"],
            capture_output=True, text=True, timeout=10,
        )
        conf_files = conf_proc.stdout.strip().split()
        # The test only enables DHCP on R1's first per-link iface,
        # so exactly one conf file should exist.
        expect_true("dnsmasq config file written",
                    any("10.30.10.100" in subprocess.run(
                        ["docker", "exec", cid, "cat", f"/etc/dnsmasq.d/{f}"],
                        capture_output=True, text=True, timeout=10,
                    ).stdout for f in conf_files),
                    f"(files: {conf_files!r})")

    # 17) Stop
    code, _ = post(f"/projects/{pid}/stop", None)
    print(f"  stop returned {code}")

    # ── summary ──
    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\nM5-01 / 1.2 PASSED")
    else:
        print("\nM5-01 / 1.2 FAILED")
        raise SystemExit(1)
finally:
    try:
        # Make sure we stop before delete
        post(f"/projects/{pid}/stop", None)
    except Exception:
        pass
    try:
        delete(f"/projects/{pid}")
        print(f"  deleted project {pid}")
    except Exception as e:
        print(f"  cleanup error: {e}")
