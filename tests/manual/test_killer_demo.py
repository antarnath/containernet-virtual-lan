"""Test the M4-08 killer demo creation.

Run with:
    python tests/manual/test_killer_demo.py
"""
import json
import time
import urllib.request as ur
import urllib.parse as up


def post(path, body=None, query=None):
    url = f"http://localhost:8000/api{path}"
    if query:
        url += "?" + up.urlencode(query)
    req = ur.Request(
        url,
        data=json.dumps(body).encode() if body else b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(ur.urlopen(req).read())


def get(path):
    return json.loads(ur.urlopen(f"http://localhost:8000/api{path}").read())


def delete(path):
    req = ur.Request(f"http://localhost:8000/api{path}", method="DELETE")
    return ur.urlopen(req).read()


# Create killer demo
print("Creating killer demo project…")
project = post("/projects", body={"name": "ignored"}, query={"template": "killer_demo"})
pid = project["id"]
print(f"  id:     {pid}")
print(f"  name:   {project['name']}")
print(f"  status: {project['status']}")
print(f"  nodes:  {project['node_count']}")
print(f"  links:  {project['link_count']}")

# Wait a moment for auto-start to settle, then refetch
time.sleep(3)
detail = get(f"/projects/{pid}")
print(f"After 3s: status={detail['status']}, nodes={detail['node_count']}, links={detail['link_count']}")

# Give it a few more seconds to see if it actually reaches running
for i in range(10):
    time.sleep(2)
    d = get(f"/projects/{pid}")
    n_running = sum(1 for n in d.get("nodes", []) if n.get("container_status") == "running")
    n_total = len(d.get("nodes", []))
    print(f"  +{(i+1)*2}s: status={d['status']}, containers running={n_running}/{n_total}")
    if d["status"] == "running" and n_running == n_total:
        break
    if d["status"] == "error":
        print(f"  ERROR: {d.get('status_detail')}")
        break

# List events to verify auto-emit
events = get(f"/projects/{pid}/events?limit=20")
if isinstance(events, dict) and "events" in events:
    events = events["events"]
print(f"\nLast {len(events)} events:")
for ev in events[:10]:
    print(f"  [{ev.get('kind'):14s}] {ev.get('summary')}")

# Clean up
print(f"\nStopping + deleting project {pid}…")
try:
    post(f"/projects/{pid}/stop")
    time.sleep(2)
except Exception as e:
    print(f"  stop: {e}")
try:
    delete(f"/projects/{pid}")
    print("  deleted.")
except Exception as e:
    print(f"  delete: {e}")

print("\nDONE")
