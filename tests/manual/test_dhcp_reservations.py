"""Test M5-01 feature 1.4: DHCP reservations (MAC → fixed IP).

Topology:
   R1 (DHCP server, has a reservation for H1) ──── H1

   R1's LAN (10.30.10.0/24) has the DHCP server pool 10.30.10.100-200.
   H1's MAC is reserved to 10.30.10.150. The test starts the project,
   reads H1's MAC from the running container, writes the reservation,
   restarts the project so the agent reloads dnsmasq config, then
   verifies:
     * R1's dnsmasq config has ``dhcp-host=H1_MAC,10.30.10.150,h1-fixed``
     * H1 actually gets 10.30.10.150 from the pool (not any other IP)
     * the API GET / PUT / DELETE for reservations all work
     * validation rejects bad MACs, IPs outside pool, duplicates

Note: we cannot reasonably test a *second* host on the same
bridge without Docker rejecting the duplicate subnet (each link
becomes its own bridge). The single-host setup covers the
contract: the reservation row → dhcp-host= line → host gets
exactly that IP.

Run with:
    python tests/manual/test_dhcp_reservations.py
"""
import ipaddress
import json
import subprocess
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
print("M5-01 / 1.4: DHCP reservations (MAC → fixed IP)")
print("=" * 50)

proj = post("/projects", {"name": "dhcp-resv-test"})
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


def container_id_for(node_id):
    proc = subprocess.run(
        ["docker", "ps", "--filter", f"label=containernet.project={pid}",
         "--filter", f"label=containernet.node={node_id}", "--format", "{{.ID}}"],
        capture_output=True, text=True, timeout=10,
    )
    ids = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
    return ids[0] if ids else None


def iface_mac_from_container(cid, iface_name):
    proc = subprocess.run(
        ["docker", "exec", cid, "cat", f"/sys/class/net/{iface_name}/address"],
        capture_output=True, text=True, timeout=10,
    )
    return (proc.stdout.strip() or "").lower() or None


def find_per_link_iface(cid, expected_subnet_prefix):
    """Return the iface name whose address is in the expected prefix."""
    proc = subprocess.run(
        ["docker", "exec", cid, "ip", "-4", "-o", "addr", "show"],
        capture_output=True, text=True, timeout=10,
    )
    for line in proc.stdout.splitlines():
        if expected_subnet_prefix in line:
            parts = line.split()
            if len(parts) >= 2:
                return parts[1].rstrip(":").rstrip("\\")
    return None


try:
    # 1) Create router + host
    r1 = post(f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = post(f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]
    print(f"  added R1, H1")

    # 2) Interfaces
    r1_lan = post(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces",
        {"name": "eth0", "ip_address": "10.30.10.1", "subnet_mask": "/24"},
    )[1]
    h1_if = post(
        f"/projects/{pid}/nodes/{h1['id']}/interfaces",
        {"name": "eth0", "subnet_mask": "/24"},
    )[1]
    print(f"  added interfaces")

    # 3) Wire up
    link_r1_h1 = post(
        f"/projects/{pid}/links",
        {"iface_a_id": r1_lan["id"], "iface_b_id": h1_if["id"]},
    )[1]
    print(f"  link(r1-h1) subnet={link_r1_h1.get('subnet_cidr')!r}")

    # 4) Enable DHCP server on R1's LAN — pool is 10.30.10.100-200
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp",
        {
            "enabled": True,
            "pool_start": "10.30.10.100",
            "pool_end": "10.30.10.200",
            "lease_time": 3600,
        },
    )
    expect("R1 DHCP server config → 200", 200, code)

    # 5) Validation: invalid MAC → 422
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
        {"reservations": [{"mac_address": "not-a-mac", "ip_address": "10.30.10.150"}]},
    )
    expect("invalid MAC → 422", 422, code)

    # 6) Validation: IP outside pool → 422
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
        {"reservations": [{"mac_address": "aa:bb:cc:dd:ee:ff",
                           "ip_address": "10.30.10.250"}]},
    )
    expect("IP outside pool → 422", 422, code)

    # 7) Validation: reservation on a non-router iface → 422
    code, body = put(
        f"/projects/{pid}/nodes/{h1['id']}/interfaces/{h1_if['id']}/dhcp/reservations",
        {"reservations": [{"mac_address": "aa:bb:cc:dd:ee:ff",
                           "ip_address": "10.30.10.150"}]},
    )
    expect("reservation on host → 422", 422, code)

    # 8) Empty list works
    code, body = put(
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
        {"reservations": []},
    )
    expect("empty list → 200", 200, code)
    expect("empty list → reservations=[]", [], body.get("reservations"))

    # 9) Start the project so we can read H1's MAC
    print("  starting project…")
    code, body = post(f"/projects/{pid}/start", None)
    if code not in (200, 202):
        print(f"  ✗ start failed: {code} {body}")
        failed += 1
        raise SystemExit(1)
    print(f"  start returned {code}")

    # 10) Wait for running
    deadline = time.time() + 90
    project = None
    while time.time() < deadline:
        project = get(f"/projects/{pid}")
        if project["status"] == "running":
            break
        time.sleep(2)
    expect("project reached 'running'", "running",
           project["status"] if project else None)

    # 11) Read H1's MAC
    h1_cid = container_id_for(h1["id"])
    r1_cid = container_id_for(r1["id"])
    expect_true("H1 container is running", h1_cid is not None)
    expect_true("R1 container is running", r1_cid is not None)

    h1_iface = find_per_link_iface(h1_cid, "10.30.10.") if h1_cid else None
    print(f"  H1 iface in container: {h1_iface}")
    h1_mac = iface_mac_from_container(h1_cid, h1_iface) if h1_iface else None
    print(f"  H1 MAC: {h1_mac}")
    expect_true("H1 MAC looks valid", h1_mac and ":" in h1_mac,
                f"(got {h1_mac!r})")

    # 12) Set the reservation: H1 → 10.30.10.150, with hostname h1-fixed
    if h1_mac:
        code, body = put(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
            {"reservations": [{
                "mac_address": h1_mac,
                "ip_address": "10.30.10.150",
                "hostname": "h1-fixed",
            }]},
        )
        expect("set reservation for H1 → 200", 200, code)
        expect("reservation has 1 entry", 1,
               len(body.get("reservations", [])))
        if body.get("reservations"):
            r0 = body["reservations"][0]
            expect("reservation MAC persisted", h1_mac, r0.get("mac_address"))
            expect("reservation IP persisted", "10.30.10.150",
                   r0.get("ip_address"))
            expect("reservation hostname persisted", "h1-fixed",
                   r0.get("hostname"))

        # 13) Duplicate MAC in body → 422
        code, body = put(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
            {"reservations": [
                {"mac_address": h1_mac, "ip_address": "10.30.10.150"},
                {"mac_address": h1_mac, "ip_address": "10.30.10.151"},
            ]},
        )
        expect("duplicate MAC in body → 422", 422, code)

        # 14) Duplicate IP in body → 422 (two reservations, same IP)
        code, body = put(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
            {"reservations": [
                {"mac_address": h1_mac, "ip_address": "10.30.10.150"},
                {"mac_address": "11:22:33:44:55:66", "ip_address": "10.30.10.150"},
            ]},
        )
        expect("duplicate IP in body → 422", 422, code)

        # 14b) Re-set the H1 reservation (the duplicate test left
        # it cleared; we need it back for the agent push later).
        code, body = put(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations",
            {"reservations": [{
                "mac_address": h1_mac,
                "ip_address": "10.30.10.150",
                "hostname": "h1-fixed",
            }]},
        )
        expect("re-set reservation for H1 → 200", 200, code)

        # 15) GET the list
        list_body = get(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations"
        )
        expect("GET reservations returns 1 entry", 1,
               len(list_body.get("reservations", [])))

    # 16) Restart the project so the agent reloads dnsmasq config
    print("  restarting project to push reservations to agent…")
    code, _ = post(f"/projects/{pid}/stop", None)
    print(f"  stop returned {code}")
    deadline = time.time() + 30
    while time.time() < deadline:
        project = get(f"/projects/{pid}")
        if project["status"] == "stopped":
            break
        time.sleep(1)
    expect("project stopped", "stopped",
           project["status"] if project else None)

    code, _ = post(f"/projects/{pid}/start", None)
    print(f"  start returned {code}")
    deadline = time.time() + 60
    while time.time() < deadline:
        project = get(f"/projects/{pid}")
        if project["status"] == "running":
            break
        time.sleep(2)
    expect("project re-running", "running",
           project["status"] if project else None)

    # 17) Wait for udhcpc + reservation round-trip
    print("  waiting 20s for udhcpc + reservation…")
    time.sleep(20)

    r1_cid = container_id_for(r1["id"])
    h1_cid = container_id_for(h1["id"])
    expect_true("R1 container is running (after restart)",
                r1_cid is not None)
    expect_true("H1 container is running (after restart)",
                h1_cid is not None)

    if r1_cid:
        # 18) Verify R1's dnsmasq config has the dhcp-host line
        r1_conf = subprocess.run(
            ["docker", "exec", r1_cid, "cat", "/etc/dnsmasq.d/eth1.conf"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        print(f"  R1 conf:\n    " + r1_conf.replace("\n", "\n    "))
        if h1_mac:
            expect_true(f"R1 conf has dhcp-host={h1_mac}",
                        f"dhcp-host={h1_mac}" in r1_conf,
                        f"(conf: {r1_conf!r})")
            expect_true("R1 conf binds to 10.30.10.150",
                        "10.30.10.150" in r1_conf)
            expect_true("R1 conf has hostname h1-fixed",
                        "h1-fixed" in r1_conf)

        # 19) R1's leases file should have H1 at 10.30.10.150
        r1_leases = subprocess.run(
            ["docker", "exec", r1_cid, "cat",
             "/var/lib/misc/dnsmasq.leases"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        print(f"  R1 leases:\n    " + r1_leases.replace("\n", "\n    "))
        r1_lease_ips = []
        for line in r1_leases.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    r1_lease_ips.append(ipaddress.IPv4Address(parts[2]))
                except ValueError:
                    pass
        in_pool = [ip for ip in r1_lease_ips
                   if ip in ipaddress.ip_network("10.30.10.0/24")]
        expect_true("R1 has >=1 lease in 10.30.10.0/24", len(in_pool) >= 1,
                    f"(got {[str(ip) for ip in r1_lease_ips]})")

        # 20) The reservation guarantee: if H1 is in the leases,
        # it MUST be 10.30.10.150.
        if h1_mac:
            h1_lease_ip = None
            for line in r1_leases.splitlines():
                if h1_mac in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            h1_lease_ip = ipaddress.IPv4Address(parts[2])
                        except ValueError:
                            pass
                    break
            expect("H1 got the reserved IP 10.30.10.150",
                   ipaddress.IPv4Address("10.30.10.150"),
                   h1_lease_ip)

    # 21) H1's actual interface IP should be 10.30.10.150
    if h1_cid:
        h1_iface = find_per_link_iface(h1_cid, "10.30.10.") if h1_cid else None
        if h1_iface:
            h1_ip_now = subprocess.run(
                ["docker", "exec", h1_cid, "ip", "-4", "-o", "addr",
                 "show", "dev", h1_iface],
                capture_output=True, text=True, timeout=10,
            ).stdout
            print(f"  H1 ip now: {h1_ip_now.strip()!r}")
            expect_true("H1's iface IP is 10.30.10.150",
                        "10.30.10.150" in h1_ip_now,
                        f"(got: {h1_ip_now!r})")

    # 22) DELETE the reservation by id
    if r1_cid:
        list_body = get(
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations"
        )
        if list_body.get("reservations"):
            res_id = list_body["reservations"][0]["id"]
            req = ur.Request(
                f"{BASE}/projects/{pid}/nodes/{r1['id']}/interfaces/"
                f"{r1_lan['id']}/dhcp/reservations/{res_id}",
                method="DELETE",
            )
            try:
                resp = ur.urlopen(req, timeout=30)
                code = resp.getcode()
            except urllib.error.HTTPError as e:
                code = e.code
            expect(f"DELETE reservation {res_id[:8]}… → 204", 204, code)

            # 23) After delete, list is empty
            after = get(
                f"/projects/{pid}/nodes/{r1['id']}/interfaces/{r1_lan['id']}/dhcp/reservations"
            )
            expect("after delete: 0 reservations", 0,
                   len(after.get("reservations", [])))

    # 24) Stop
    code, _ = post(f"/projects/{pid}/stop", None)
    print(f"  stop returned {code}")

    # ── summary ──
    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\nM5-01 / 1.4 PASSED")
    else:
        print("\nM5-01 / 1.4 FAILED")
        raise SystemExit(1)
finally:
    try:
        post(f"/projects/{pid}/stop", None)
    except Exception:
        pass
    try:
        delete(f"/projects/{pid}")
        print(f"  deleted project {pid}")
    except Exception as e:
        print(f"  cleanup error: {e}")
