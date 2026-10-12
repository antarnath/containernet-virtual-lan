"""Test M5-01 feature 1.1: default gateway auto-suggest.

Build a 1-router + 1-host topology where the user does NOT type a
gateway. Verify the host container ends up with the router's
interface IP as its default route.

Run with:
    python tests/manual/test_default_gateway_auto.py
"""
import json
import subprocess
import time
import urllib.parse as up
import urllib.request as ur


BASE = "http://localhost:8000/api"


# ── HTTP helpers ──────────────────────────────────────────────────────
def _req(method, path, body=None, query=None):
    url = f"{BASE}{path}"
    if query:
        url += "?" + up.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = ur.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return json.loads(ur.urlopen(req).read())


def post(path, body=None, query=None):
    return _req("POST", path, body, query)


def get(path):
    return _req("GET", path)


def patch(path, body):
    return _req("PATCH", path, body)


def delete(path):
    req = ur.Request(f"{BASE}{path}", method="DELETE")
    return ur.urlopen(req).read()


# ── docker helpers ────────────────────────────────────────────────────
def _container_for_node(node_id):
    """Resolve a project node id to a docker container name.

    Node containers are named ``cn-<proj8>-<kind3>-<node6>``. We
    can pull the short forms from the project detail response.
    """
    # We need the project id to build the name. Caller passes the
    # project back; we accept a list of nodes and find ours.
    raise NotImplementedError  # use _container_for_node_in_project


def _container_for_node_in_project(node, project_id):
    short_p = project_id.replace("-", "")[:8]
    short_n = node["id"].replace("-", "")[:6]
    kind_short = node["kind"][:3]
    return f"cn-{short_p}-{kind_short}-{short_n}"


def _docker_exec(container_name, cmd):
    """Run ``cmd`` inside ``container_name`` and return (rc, stdout, stderr)."""
    p = subprocess.run(
        ["docker", "exec", container_name, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=10,
    )
    return p.returncode, p.stdout, p.stderr


# ── the test ──────────────────────────────────────────────────────────
print("M5-01 / 1.1: default-gateway auto-suggest")
print("=" * 50)

# 1) Create a blank project
proj = post("/projects", body={"name": "gw-auto-test"})
pid = proj["id"]
print(f"  created project {pid}")

try:
    # 2) Add 1 router + 1 host
    router = post(f"/projects/{pid}/nodes", body={"kind": "router", "name": "R1"})
    host = post(f"/projects/{pid}/nodes", body={"kind": "host", "name": "H1"})
    print(f"  added router {router['id']} and host {host['id']}")

    # 3) Add one interface to each
    # Router: 10.0.0.1/24
    r_iface = post(
        f"/projects/{pid}/nodes/{router['id']}/interfaces",
        body={"name": "eth0", "ip_address": "10.0.0.1", "subnet_mask": "/24"},
    )
    # Host: 10.0.0.10/24, NO gateway typed
    h_iface = post(
        f"/projects/{pid}/nodes/{host['id']}/interfaces",
        body={"name": "eth0", "ip_address": "10.0.0.10", "subnet_mask": "/24"},
    )
    print(f"  added interfaces: router={r_iface['id']} host={h_iface['id']}")

    # 4) Wire them
    link = post(
        f"/projects/{pid}/links",
        body={"iface_a_id": r_iface["id"], "iface_b_id": h_iface["id"]},
    )
    print(f"  wired: link {link['id']}")

    # 5) Start
    print("  starting project…")
    post(f"/projects/{pid}/start")
    print("  start requested")

    # 6) Wait for running
    running = False
    for i in range(15):
        time.sleep(2)
        d = get(f"/projects/{pid}")
        if d["status"] == "running":
            running = True
            print(f"  +{(i+1)*2}s: status=running")
            break
        if d["status"] == "error":
            print(f"  ERROR: {d.get('status_detail', '?')}")
            raise SystemExit(1)
    if not running:
        print(f"  did not reach running; status={d['status']}")
        raise SystemExit(1)

    # 7) Find the host container, exec `ip route` inside
    detail = get(f"/projects/{pid}")
    host_node = next(n for n in detail["nodes"] if n["kind"] == "host")
    container = _container_for_node_in_project(host_node, pid)
    print(f"  exec'ing into {container}")

    rc, out, err = _docker_exec(container, "ip route show default")
    if rc != 0:
        print(f"  FAIL: docker exec returned {rc}: {err}")
        raise SystemExit(1)
    print(f"  default route inside container: {out.strip()}")

    # 8) Verify default route points at the router's IP
    expected_gw = "10.0.0.1"
    if expected_gw not in out:
        print(f"  FAIL: expected default via {expected_gw}, got: {out!r}")
        raise SystemExit(1)
    if "default" not in out:
        print(f"  FAIL: no 'default' route found: {out!r}")
        raise SystemExit(1)
    print(f"  ✓ default route is via {expected_gw}")

    # 9) Verify the host can actually ping the router
    rc, out, err = _docker_exec(
        container,
        f"ping -c 1 -W 2 {expected_gw}",
    )
    if rc != 0:
        print(f"  FAIL: ping returned {rc}: stdout={out!r} stderr={err!r}")
        raise SystemExit(1)
    print(f"  ✓ host can ping {expected_gw}")

    print("\nM5-01 / 1.1 PASSED")
finally:
    # Cleanup
    try:
        post(f"/projects/{pid}/stop")
        time.sleep(1)
    except Exception:
        pass
    try:
        delete(f"/projects/{pid}")
        print(f"  deleted project {pid}")
    except Exception as e:
        print(f"  cleanup error: {e}")
