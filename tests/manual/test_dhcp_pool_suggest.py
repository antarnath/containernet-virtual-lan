"""GET .../interfaces/<iid>/dhcp/suggest — auto-filled DHCP pool.

Configuring a DHCP server meant typing four fields per interface
(pool start, pool end, lease time, DNS), and three of them are fully
derivable from what the user had already set up: the interface's own
address and its link's subnet. Worse, the rules the validator enforces
aren't guessable, so hand-typed pools failed in ways that looked like
the UI was broken.

This test pins the suggestion contract, and — more importantly — that
every value it returns would actually PASS the real validator. A
suggestion that the save path then rejects is worse than no
suggestion at all, so we run it back through PUT.

The rule that matters most: the pool must start at .100. A DHCP client
holds a .2 placeholder before it has a lease (the kernel needs a
source address to emit DHCPDISCOVER), and that placeholder is only
safe because the pool starts well above it. A suggestion starting at
.2 would let dnsmasq lease the placeholder away.

Run with:
    python3 tests/manual/test_dhcp_pool_suggest.py
"""
import ipaddress
import json
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


print("DHCP pool suggestion")
print("=" * 52)

pid = _req("POST", "/projects", {"name": "dhcp-suggest-test"})[1]["id"]
print(f"  created project {pid}")

try:
    r1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "router", "name": "R1"})[1]
    h1 = _req("POST", f"/projects/{pid}/nodes", {"kind": "host", "name": "H1"})[1]

    ri_a = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth0", "ip_address": "10.60.10.1",
                 "subnet_mask": "/24"})[1]
    ri_b = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth1", "ip_address": "10.60.20.1",
                 "subnet_mask": "/24"})[1]
    h1i = _req("POST", f"/projects/{pid}/nodes/{h1['id']}/interfaces",
               {"name": "eth0", "subnet_mask": "/24"})[1]
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_a["id"], "iface_b_id": h1i["id"]})
    _req("POST", f"/projects/{pid}/links",
         {"iface_a_id": ri_b["id"], "iface_b_id": h1i["id"]})

    suggestions = {}

    def suggest(node_id, iface_id):
        code, body = _req(
            "GET",
            f"/projects/{pid}/nodes/{node_id}/interfaces/{iface_id}/dhcp/suggest",
        )
        return code, body

    # ─── the two ordinary interfaces ─────────────────────────────
    print("\n  -- ordinary /24 interfaces --")
    for iface, subnet in ((ri_a, "10.60.10.0/24"), (ri_b, "10.60.20.0/24")):
        code, s = suggest(r1["id"], iface["id"])
        expect(f"{iface['name']} → 200", code == 200, f"(got {code}: {s})")
        if code != 200:
            continue
        suggestions[iface["name"]] = s

        own = ipaddress.ip_address(iface["ip_address"])
        ps = ipaddress.ip_address(s["pool_start"])
        pe = ipaddress.ip_address(s["pool_end"])
        net = ipaddress.ip_network(subnet)

        print(f"     {iface['name']}: {s['pool_start']} - {s['pool_end']}, dns={s['dns']}")

        expect(f"{iface['name']} pool_start inside {subnet}",
               ps in net, f"(got {ps})")
        expect(f"{iface['name']} pool_end inside {subnet}",
               pe in net, f"(got {pe})")
        expect(f"{iface['name']} pool_start < pool_end", ps < pe, f"(got {ps}, {pe})")
        expect(f"{iface['name']} excludes the router's own IP",
               not (ps <= own <= pe), f"(router {own} inside {ps}-{pe})")

        # The invariant the placeholder depends on.
        expect(f"{iface['name']} pool clears the .2 placeholder",
               int(ps) > int(net.network_address) + 2,
               f"(pool starts at {ps}; a client holds "
               f"{net.network_address + 2} until it leases)")
        expect(f"{iface['name']} pool starts at or above .100",
               (int(ps) - int(net.network_address)) >= 100,
               f"(got {ps}, offset "
               f"{int(ps) - int(net.network_address)})")

        expect(f"{iface['name']} DNS is the gateway", s["dns"] == iface["ip_address"],
               f"(got {s['dns']}, gateway is {iface['ip_address']})")
        expect(f"{iface['name']} echoes the subnet", s["subnet_cidr"] == subnet,
               f"(got {s['subnet_cidr']})")
        expect(f"{iface['name']} explains itself", len(s.get("why", "")) > 10,
               f"(got {s.get('why')!r})")

    # ─── the suggestion must survive the real validator ──────────
    #
    # This is the assertion that matters most. A pre-fill that Save
    # then rejects is a worse bug than no pre-fill, so send the
    # suggested values straight back through PUT /dhcp.
    print("\n  -- suggested values pass the real validator --")
    for name, s in suggestions.items():
        iface = ri_a if name == "eth0" else ri_b
        code, body = _req(
            "PUT",
            f"/projects/{pid}/nodes/{r1['id']}/interfaces/{iface['id']}/dhcp",
            {"enabled": True, "pool_start": s["pool_start"],
             "pool_end": s["pool_end"], "lease_time": 43200,
             "dns": s["dns"]},
        )
        expect(f"PUT accepts the {name} suggestion", code == 200,
               f"(got {code}: {body})")
        if code == 200:
            expect(f"{name} persisted the suggested pool",
                   body.get("dhcp_pool_start") == s["pool_start"]
                   and body.get("dhcp_pool_end") == s["pool_end"],
                   f"(got {body.get('dhcp_pool_start')}-"
                   f"{body.get('dhcp_pool_end')})")
            expect(f"{name} persisted the suggested DNS",
                   body.get("dhcp_dns") == s["dns"],
                   f"(got {body.get('dhcp_dns')})")

    # ─── an interface with no address can't be suggested ─────────
    print("\n  -- states with no derivable pool --")
    code, body = suggest(r1["id"], ri_b["id"])
    # ri_b is now configured; the endpoint still derives from the
    # topology, so it should still answer.
    expect("suggestion works on a configured interface too",
           code == 200, f"(got {code}: {body})")

    # An interface with no IP at all has nothing to derive from.
    bare = _req("POST", f"/projects/{pid}/nodes/{r1['id']}/interfaces",
                {"name": "eth9", "subnet_mask": "/24"})[1]
    code, body = suggest(r1["id"], bare["id"])
    expect("interface with no IP → 422", code == 422, f"(got {code}: {body})")
    detail = (body or {}).get("detail") or {}
    expect("422 names the reason", detail.get("error") == "cannot_suggest",
           f"(got {detail})")
    expect("422 message is actionable",
           "IP" in str(detail.get("message", "")),
           f"(got {detail.get('message')!r})")

    # ─── an unwired interface has no subnet to fit a pool in ─────
    code, body = suggest(r1["id"], bare["id"])
    expect("unwired interface → 422", code == 422, f"(got {code})")

    # ─── unknown ids ─────────────────────────────────────────────
    code, _ = _req(
        "GET",
        f"/projects/{pid}/nodes/{r1['id']}/interfaces/"
        "00000000-0000-0000-0000-000000000000/dhcp/suggest",
    )
    expect("unknown interface → 404", code == 404, f"(got {code})")

    code, _ = _req(
        "GET",
        "/projects/00000000-0000-0000-0000-000000000000"
        f"/nodes/{r1['id']}/interfaces/{ri_a['id']}/dhcp/suggest",
    )
    expect("unknown project → 404", code == 404, f"(got {code})")

    print()
    print(f"  passed: {passed}, failed: {failed}")
    if failed == 0:
        print("\nPool suggestion PASSED")
    else:
        print("\nPool suggestion FAILED")
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