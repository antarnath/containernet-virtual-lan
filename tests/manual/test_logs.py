"""Test the M4-07 Logs view end-to-end.

Run with:
    python tests/manual/test_logs.py
"""
import json
import time
import urllib.request as ur


def post(path, body):
    req = ur.Request(
        f"http://localhost:8000/api{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(ur.urlopen(req).read())


def get(path):
    return json.loads(ur.urlopen(f"http://localhost:8000/api{path}").read())


def list_events(pid, **kwargs):
    qs = "&".join(f"{k}={v}" for k, v in kwargs.items())
    return get(f"/projects/{pid}/events?{qs}")


# Create project
project = post("/projects", {"name": "logs-test"})
project_id = project["id"]
print("project:", project_id[:8])

# Add host + router
host = post(f"/projects/{project_id}/nodes", {"kind": "host", "name": "h1"})
router = post(f"/projects/{project_id}/nodes", {"kind": "router", "name": "r1"})

# Add interfaces to each
iface_a = post(f"/projects/{project_id}/nodes/{host['id']}/interfaces", {
    "name": "eth0", "ip_address": "10.0.0.1", "subnet_mask": "/24",
})
iface_b = post(f"/projects/{project_id}/nodes/{router['id']}/interfaces", {
    "name": "eth0", "ip_address": "10.0.0.2", "subnet_mask": "/24",
})

# Wire them
link = post(
    f"/projects/{project_id}/links",
    {"iface_a_id": iface_a["id"], "iface_b_id": iface_b["id"]},
)
print("link:", link["id"][:8])

# Start
res = post(f"/projects/{project_id}/start", {})
print("start status:", res.get("status"), "errors:", res.get("errors"))

# Wait for events to be written
time.sleep(1.5)
evs = list_events(project_id, limit=20)
print(f"\nEvents after start ({len(evs['events'])}):")
for e in evs["events"]:
    print(f"  - {e['kind']:20s} | {e['summary']}")

# Filter to just lifecycle
evs_life = list_events(project_id, kind="lifecycle", limit=10)
print(f"\nLifecycle events ({len(evs_life['events'])}):")
for e in evs_life["events"]:
    print(f"  - {e['kind']:20s} | {e['summary']}")

# Stop
res = post(f"/projects/{project_id}/stop", {})
print("\nstop status:", res.get("status"))

time.sleep(1.5)
evs = list_events(project_id, limit=30)
print(f"\nAll events after stop ({len(evs['events'])}):")
for e in evs["events"]:
    print(f"  - {e['kind']:20s} | {e['summary']}")
