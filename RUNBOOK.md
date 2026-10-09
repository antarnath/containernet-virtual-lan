# Runbook

> The on-call contributor's pocket reference. If something is on
> fire, start here. If something is missing from here, file an
> issue — the runbook is meant to grow.

This is intentionally not a tutorial. See `README.md` for the
product, `architecture.md` for how it fits together, and
`phases/milestone-4/` for the build plan.

---

## 1. Quick triage

| Symptom                                          | Go to                                                |
|--------------------------------------------------|------------------------------------------------------|
| Frontend is blank                                | §2 (browser console)                                 |
| Project stuck in `starting`                      | §3 (bridge conflicts) + §6 (logs view)               |
| Containers up but packets don't cross            | §4 (router config)                                   |
| Attacker panel says "can't reach :9092"          | §5 (LAN attach)                                      |
| Orphan `cn-` containers / networks piling up     | §7 (orphan sweeper)                                  |
| A specific node is `error`                       | §6 (logs view) + `docker logs <cn-…>`                |
| Capture container won't start                    | §8 (capture permissions)                             |

---

## 2. Frontend won't load

```bash
# 1. Is the backend healthy?
curl http://localhost:8000/api/projects

# 2. Is the frontend container up?
docker ps --format '{{.Names}} {{.Status}}' | grep frontend

# 3. Browser console (F12). Most common issues:
#    - CORS: backend was restarted on a different port. The
#      frontend talks to whatever the nginx.conf upstream
#      points at; if that drifts, the proxy returns 502.
#    - Mixed content: frontend on http, backend on https.
#    - Stale build: rebuild the frontend image.
docker compose build frontend && docker compose up -d frontend
```

---

## 3. Bridge conflicts (`Pool overlaps`)

Each link gets its own Docker bridge (Linux bridge) with a
subnet derived from the two endpoints' IPs and masks. Docker
refuses to create two bridges on the same subnet, so:

- **Per-link subnet must be unique** within the host's Docker
  daemon. The default subnet choice (`link_service._derive_subnet`)
  picks the network address of the lower IP — that means **two
  links on the same /24 will collide if they share the lower IP
  half**. /29+ is the safe minimum (gives 6 usable hosts, room
  for endpoints + a gateway).

- **Two projects on overlapping subnets will collide.** If the
  user types `10.0.0.1/24` on every project, only the first one
  starts. Tell the user to use a different range, or use the
  demo.

Quickest fix:

```bash
make clean
make up
```

---

## 4. Router config debugging

```bash
# Get a shell on a router container
docker exec -it <cn-...-rou-...> bash

# Inside the container, you have the usual Linux networking tools:
ip route          # routing table
ip neigh          # ARP table
ip addr           # interface IPs
ip link           # link state

# The router agent exposes:
curl localhost:9090/state             # aggregated state snapshot
curl localhost:9090/state/routes      # live routing table
curl localhost:9090/state/arp         # live ARP table
curl localhost:9090/state/interfaces  # per-interface counters

# The agent is the only thing on the container with python3;
# anything not in the base image (e.g. tcpdump) needs to be
# installed into the router-base image first.
```

---

## 5. Capture container / attack control

```bash
# Per-link packet capture
docker exec -it <cn-...> tcpdump -i <bridge-short-name> -n
# or read the NDJSON file the host agent writes to:
tail -f /var/lib/containernet/captures/<short-pid>l<short-lid>.ndjson

# The attacker agent's :9092 control API:
docker exec -it <cn-...-att-...> curl localhost:9092/state
docker exec -it <cn-...-att-...> curl -X POST localhost:9092/attack \
    -H 'Content-Type: application/json' \
    -d '{"mode": "arp_spoof", "target_ip": "10.30.10.2"}'
docker exec -it <cn-...-att-...> curl -X POST localhost:9092/attack/stop
```

The **backend's** attack_proxy reaches the agent over the shared
`containernet_lan` network, NOT the host port. The agent's
container port 9092 is not published to the host. If you want to
debug it from outside the container, use the exec pattern above.

---

## 6. Logs view + backend logs

The in-app **Logs view** (`/projects/:id/logs`) is the single
pane of glass. Every lifecycle event, every bridge create, every
node start, every message, every anomaly, every attack signal
shows up there with a timestamp and an expand-for-detail
button. Use the filter chips at the top to narrow.

If the in-app view is missing events, check the backend:

```bash
docker logs containernet_backend --tail 200 | grep -iE "error|exception"
```

The backend also broadcasts events over a per-project WebSocket
channel (`/api/projects/:id/ws`). The frontend's `realtimeStore`
is the canonical consumer; debug it with the browser's network
panel.

---

## 7. Orphan sweeper

The sweeper runs every 60 seconds (see
`backend/app/services/orphan_sweeper.py`). It looks for containers
with the `containernet.host=true` or `containernet.router=true`
label, and removes any whose owning project is not in the
`running` state.

The sweeper is **conservative**: it never touches a container
whose project is alive and running. If the project is in any
other state (`stopped`, `error`, `partial`, `draft`), the
container is considered an orphan and removed.

**What it does NOT clean up**: orphaned bridges (Docker networks
with the `containernet.link=true` or `containernet.project=true`
labels). If a project was force-deleted, the bridges may stick
around. Wipe them manually:

```bash
docker network prune -f --filter "label=containernet.link=true"
```

Or just `make clean`.

---

## 8. Capture container won't start

Per-link packet capture is done by a sidecar container attached
to the same bridge. It writes to a bind-mounted directory at
`/var/lib/containernet/captures/`. If that directory is not
writable by the container's UID, the capture dies on start.

```bash
# Permissions check
ls -ld /var/lib/containernet/captures
# Should be writable by the host-agent's UID (root in the image)

# If the directory doesn't exist:
mkdir -p /var/lib/containernet/captures
chmod 777 /var/lib/containernet/captures
```

---

## 9. Common failures

### "Router can't reach the backend"

The router container is NOT attached to `containernet_lan`
(only host / server / attacker are). It still works — it just
doesn't send heartbeats, and the anomaly detector polls it via
`router_proxy` over the project's per-link bridges. If you see
"can't reach the backend" in the router logs, check that the
agent's `BACKEND_URL` env is set correctly in
`router-agent/kind_env()` and that the per-link bridges are up.

### "Canvas won't load"

- Browser console. Look for CORS, 502 from the Nginx proxy, or
  a stale build.
- `docker compose logs frontend` for proxy errors.
- `curl http://localhost:8000/api/projects` from the host. If
  that returns JSON, the backend is fine.

### "Project stuck in `starting`"

- Hit the Logs view (or `GET /api/projects/:id/events`); the
  first error will be at the top.
- Most common: bridge conflict (§3), or a container image that
  doesn't exist (`docker images | grep containernet`).
- Use `make clean` to reset.

### "Live capture shows no packets"

- The capture container might be off. Check
  `/var/lib/containernet/captures/`.
- The interface filter might be wrong. The agent captures
  everything on the bridge (in promiscuous mode) — the per-link
  filter is `not src host <own-ip> and not dst host <own-ip>`.
  If the link is `down` at the kernel level, no packets appear.

### "Anomaly never fires"

- The detector polls every 1s. A `new_mac` event needs a router
  to have at least one ARP entry to compare against.
- Check `docker logs containernet_backend | grep anomaly`.

---

## 10. Reproducible clean slate

```bash
make clean
make up
# Then: http://localhost:5173 → click "⚡ Killer demo"
```

If a build step is slow, `make build` rebuilds only images
whose Dockerfiles or contexts have changed.

---

## 11. Where things live

| Concern               | File / folder                                                  |
|-----------------------|----------------------------------------------------------------|
| Spawn containers      | `backend/app/services/node_service.py`                         |
| Per-link bridges      | `backend/app/services/link_service.py`                         |
| Lifecycle             | `backend/app/services/project_lifecycle.py`                    |
| Anomaly detection     | `backend/app/services/anomaly_detector.py`                     |
| Attack detection      | `backend/app/services/attack_detector.py`                      |
| Orphan sweeper        | `backend/app/services/orphan_sweeper.py`                       |
| Realtime broadcast    | `backend/app/services/realtime.py`                             |
| 5 attack modes        | `host-agent/attack_engine.py`                                  |
| Router agent          | `router-agent/`                                                |
| Canvas / React Flow   | `frontend/src/canvas/Canvas.tsx`                               |
| Design tokens         | `phases/milestone-4/design-system.md`                          |
| Architecture          | `architecture.md`                                              |
| 5 rules               | `phases/milestone-4/overview.md` §1                            |
