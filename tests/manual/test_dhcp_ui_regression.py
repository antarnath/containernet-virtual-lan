"""Regression check for the DHCP-tab save that never persisted.

The DHCP card re-synced its form state from an ``[iface]`` effect.
The parent rebuilds those objects from ``ifaces.map(...)`` on every
render, and the leases poll re-renders every 5s — so the effect
fired on every tick and reset whatever the user had typed back to
the last-saved value (empty, on a never-configured interface). The
result was a pool field that looked filled in but was ``''`` at
submit time, so validation rejected it with "Pool start must be a
dotted IPv4" and nothing ever persisted.

This exercises the exact API sequence the panel issues, to prove the
backend side of that flow is sound and the fault was purely
client-side state management.

Run with:
    python3 tests/manual/test_dhcp_ui_regression.py
"""
import json
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


def expect(label, expected, actual):
    global passed, failed
    if actual == expected:
        print(f"  ✓ {label}: {actual!r}")
        passed += 1
    else:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        failed += 1


print("DHCP tab save regression")
print("=" * 50)

pid = _req("POST", "/projects", {"name": "dhcp-ui-regression"})[1]["id"]
print(f"  created project {pid}")

try:
    r1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]

    ri = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
              {"name": "eth0", "ip_address": "10.31.10.1", "subnet_mask": "/24"})[1]
    # Host interface deliberately has no ip_address — that emptiness
    # is what marks it as a DHCP client.
    h1i = _req("POST", f"/projects/{pid}/nodes/{h1['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri["id"], "iface_b_id": h1i["id"]})

    # A never-configured interface must report a null pool, which is
    # what the client seeded its form state from.
    iface_now = _req("GET", f"/projects/{pid}")[1]
    router = [n for n in iface_now["nodes"] if n["kind"] == "router"][0]
    before = router["interfaces"][0]
    expect("fresh interface has null pool_start", None, before.get("dhcp_pool_start"))
    expect("fresh interface has null pool_end", None, before.get("dhcp_pool_end"))
    expect("fresh interface has dhcp disabled", False, before.get("dhcp_enabled"))

    # The exact payload the DHCP tab sends on Save.
    code, body = _req("PUT", f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
                      {"enabled": True,
                       "pool_start": "10.31.10.100",
                       "pool_end": "10.31.10.200",
                       "lease_time": 43200,
                       "dns": "8.8.8.8"})
    expect("save → 200", 200, code)
    expect("pool_start persisted", "10.31.10.100", body.get("dhcp_pool_start"))
    expect("pool_end persisted", "10.31.10.200", body.get("dhcp_pool_end"))
    expect("dhcp_enabled persisted", True, body.get("dhcp_enabled"))

    # Re-read through the project payload the way the panel does,
    # so the value the form would re-seed from is proven present.
    after = [n for n in _req("GET", f"/projects/{pid}")[1]["nodes"]
             if n["kind"] == "router"][0]["interfaces"][0]
    expect("re-read pool_start survives", "10.31.10.100", after.get("dhcp_pool_start"))
    expect("re-read dhcp_enabled survives", True, after.get("dhcp_enabled"))

    # A second save over the same interface — this is the case that
    # used to break when the effect clobbered state mid-edit.
    code, body = _req("PUT", f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
                      {"enabled": True,
                       "pool_start": "10.31.10.110",
                       "pool_end": "10.31.10.180",
                       "lease_time": 3600})
    expect("second save → 200", 200, code)
    expect("pool_start updated", "10.31.10.110", body.get("dhcp_pool_start"))

    # Turning it off must clear the pool, not leave a stale one.
    code, body = _req("PUT", f"/projects/{pid}/nodes/{r1['id']}/interfaces/{ri['id']}/dhcp",
                      {"enabled": False})
    expect("disable → 200", 200, code)
    expect("pool_start cleared", None, body.get("dhcp_pool_start"))

    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\nDHCP UI save regression PASSED")
    else:
        print("\nDHCP UI save regression FAILED")
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