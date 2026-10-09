# ContainerNet

> **A Docker-based Cisco Packet Tracer.**
> Draw a network on a blank canvas; the system materializes it as
> real Docker containers and bridges. Send traffic, capture packets,
> fire attacks, watch the network react — all live, all in your
> browser.

ContainerNet is a teaching tool for networking and network security.
The user is the engineer: there are no templates to pick from, the
canvas always starts blank, and every node on the canvas becomes a
real Linux container wired to the rest of the lab by real Linux
bridges. Live packet capture, live attack scenarios, and live
detection signals turn the canvas into a sandbox where the same
hands-on intuition you get from a physical lab is available from a
browser tab.

The 5 attack modes (unknown host, duplicate IP, ARP spoof, TCP
SYN flood, HTTP flood) ship with teaching cards, so the same
project is also a self-paced lab for learning how those attacks
look on the wire.

---

## Quickstart

```bash
git clone <repo> containernet
cd containernet
docker compose up -d --build
```

Then open <http://localhost:5173>. The first run compiles the
`host-base` image from source — give it a few minutes.

On the empty projects page, click **⚡ Killer demo**. The system
creates a 4-node ARP-spoof MITM lab (router + 2 hosts + attacker)
and auto-starts it; within ~10 seconds you land on a running
canvas with live packet capture on the attacker's link and a
"new MAC" anomaly firing in real time.

Press `?` on the canvas for the keyboard shortcuts.

---

## What's in the box

ContainerNet ships 9 M4 phases. Every one runs against live
containers — there is no "demo mode".

| # | Capability                    | Surface                              | What you do                                                                  |
|---|-------------------------------|--------------------------------------|------------------------------------------------------------------------------|
| 1 | **Blank-canvas editor**       | `/projects`                          | Drop hosts, routers, switches, attackers. Drag to position. Click a wire to type IPs. |
| 2 | **One container per node**    | Canvas header                        | Click **Start**; the system spawns one `containernet-*` container per node.   |
| 3 | **One bridge per wire**       | Docker network list                  | Each wire is its own Linux bridge. Two projects can never see each other's traffic. |
| 4 | **Live router panel**         | Click a router node                  | Watch routes, ARP table, and interfaces stream in over WebSocket.              |
| 5 | **Send traffic**              | `+ Send` button on canvas            | Pick a source / dest / protocol, fire a real HTTP request across the topology. |
| 6 | **Wire view (per-link capture)** | Click a wire                      | Live NDJSON packet stream with protocol colour-coding.                        |
| 7 | **Attacks view**              | Click an attacker node or `/attacks` | Pick a mode (arp_spoof, tcp_flood, …), start, watch the anomaly detector fire. |
| 8 | **Logs view**                 | `≡ Logs` button on canvas            | Live timeline of every lifecycle / wire / message / anomaly / attack event.   |
| 9 | **Killer demo**               | First-time UX on `/projects`         | One-click 60-second ARP-spoof MITM scenario.                                  |

See [`phases/milestone-4/overview.md`](./phases/milestone-4/overview.md)
for the full phase plan and [`architecture.md`](./architecture.md) for
how the pieces fit together.

---

## Screens

| Projects home (empty)            | Canvas (running)                       | Wire view (live capture)             |
|----------------------------------|----------------------------------------|--------------------------------------|
| *(see `docs/screens/projects.png`)* | *(see `docs/screens/canvas.png`)*        | *(see `docs/screens/wire.png`)*        |

Screenshots are stored in `docs/screens/`. The dark theme is the
contract — see [`phases/milestone-4/design-system.md`](./phases/milestone-4/design-system.md).

---

## How it works

A project's life cycle, end to end:

1. **You draw a network.** Drop nodes, drag to position, click a
   wire to type IPs and subnet masks. Five node kinds (`host`,
   `server`, `switch`, `router`, `attacker`) and three wire states
   (unconfigured, IP-only, fully wired).
2. **You click Start.** The backend talks to the Docker daemon
   over the mounted Unix socket. It creates one bridge per wire
   (with a /29+ subnet that leaves room for a gateway), spawns
   one container per node, attaches each container to the bridges
   it participates in, and pins the IPs the user typed. Routers
   are spawned with `net.ipv4.ip_forward=1`.
3. **Containers heartbeat.** Every container runs the same
   `host-agent` process. It exposes a small HTTP API on `:8080`
   (host/server/attacker) or `:9090` (router), and reports
   heartbeats, metrics, and the agent's own state back to the
   backend over the shared `containernet_lan` network.
4. **Anomalies + attack signals.** A background detector on the
   backend polls every container every second, compares to
   thresholds, and broadcasts over WebSocket. The frontend shows
   them as red rings on the canvas and as a feed in the Attacks
   view.
5. **You read the logs.** The Logs view is an SSE / WebSocket
   timeline of every event in the project — lifecycle, bridges,
   node spawns, messages, anomalies, attack signals, errors. Use
   it as the single pane of glass when something goes wrong.

```
User (browser)
    │  HTTP / WebSocket / SSE
    ▼
React dashboard (Vite + TypeScript + React Flow + Zustand)
    │  REST + WS (per-project subscribe envelope)
    ▼
FastAPI backend (Python + SQLAlchemy + asyncpg)
    ├── 5-primitive model: Project, ProjectNode, ProjectInterface, ProjectLink, ProjectEvent
    ├── Lifecycle service (start / stop / restart)
    ├── Per-link bridge + per-link packet capture
    ├── Host agent runtime (spawned inside every container)
    ├── Anomaly detector (polls routers every 1s)
    ├── Attack detector (polls attacker :9092 every 1s)
    ├── Orphan sweeper (every 60s, cleans up half-started projects)
    └── Realtime broadcaster (WebSocket + SSE subscribers)
            │
            ├──► PostgreSQL (projects, nodes, interfaces, links, events)
            └──► Docker daemon (/var/run/docker.sock)
                       │
                       ▼
                One bridge per wire:
                  cn<short-pid>ppl<short-lid>   ── isolated /29+, only the two endpoints
                  containernet_lan             ── shared with the backend (heartbeats)
```

### The 5 rules

1. **No templates.** The canvas is always blank. The one-click
   "Killer demo" is a single-endpoint exception, not a template
   picker.
2. **Design system is a contract.** Every screen uses the tokens
   in `phases/milestone-4/design-system.md`. If a token doesn't
   exist, add it to the spec first.
3. **One container per node, one bridge per wire.** Always.
4. **User is the engineer.** Subnet math, MAC addresses, attack
   parameters — all the user.
5. **Acceptance test passes before phase is done.** Each phase
   file has its own `PHASE_xx_ACCEPTANCE.md` checklist.

---

## Tech stack

| Layer         | Tools                                                                            |
|---------------|----------------------------------------------------------------------------------|
| Frontend      | React 18, TypeScript, Vite, Tailwind, Zustand, React Flow, Axios. Static bundle served by Nginx. |
| Backend       | FastAPI, SQLAlchemy 2.0 (async), asyncpg, httpx, Docker SDK, aiohttp. Lifespan hook handles graceful shutdown of spawned containers. |
| Database      | PostgreSQL 15.                                                                    |
| Containers    | Python 3.11 (aiohttp, psutil, scapy) on Alpine. The `host-base` image is shared by host / server / attacker; router-agent has its own image. |
| Orchestration | Docker Compose v2.                                                                |

---

## Project layout

```
ContainerNet/
├── backend/                       # FastAPI app
│   ├── app/
│   │   ├── main.py                # FastAPI app + lifecycle hooks
│   │   ├── core/                  # docker_client, db session, settings
│   │   ├── api/                   # HTTP route modules (one per resource)
│   │   ├── models/                # SQLAlchemy ORM models
│   │   ├── schemas/               # Pydantic request/response models
│   │   └── services/              # Domain logic (projects, containers, links, …)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── wait-for-db.sh
├── frontend/                      # React + Vite dashboard
│   ├── src/
│   │   ├── api/                   # Typed REST client
│   │   ├── store/                 # Zustand stores
│   │   ├── canvas/                # React Flow surface + custom node types
│   │   ├── pages/                 # Top-level routed views
│   │   ├── panels/                # Side panels (host, router)
│   │   ├── attacks/               # Attacker panel + Attacks view + lessons
│   │   ├── logs/                  # Logs view + event row + filter
│   │   ├── trigger/               # "+ Send" modal
│   │   ├── components/            # Reusable UI (ErrorBoundary, ShortcutsModal, …)
│   │   └── types/                 # Shared TS interfaces
│   ├── Dockerfile                 # Multi-stage build → Nginx static bundle
│   ├── nginx.conf                 # /api and /ws proxy to backend
│   ├── tailwind.config.js
│   └── vite.config.ts
├── host-agent/                    # Python agent running inside every spawned host
│   ├── agent.py                   # Entrypoint: starts metrics, messages, attack control
│   ├── attack_engine.py           # 5 attack modes (scapy + aiohttp)
│   ├── attack_control.py          # :9092 control HTTP API
│   ├── config.py                  # Reads AGENT_ROLE, ATTACK_MODE, etc.
│   └── …
├── router-agent/                  # Same agent shape, but for routers
│   └── …
├── infra/
│   └── hosts/
│       ├── host-base.Dockerfile
│       └── router-base.Dockerfile
├── phases/                        # Build plan
│   ├── milestone-1/               # Archived
│   ├── milestone-2/               # Archived
│   ├── milestone-4/               # Current (9 phases)
│   └── archive/                   # Things we tried and superseded
├── docs/
│   └── screens/                   # README screenshots
├── tests/
│   └── manual/                    # End-to-end tests
├── docker-compose.yml             # db + backend + frontend
├── Makefile                       # up / down / clean / logs / test
├── RUNBOOK.md                     # On-call contributor runbook
├── architecture.md                # Canonical architecture doc
└── README.md                      # You are here
```

---

## Configuration

All configuration is via environment variables on the `backend`
service (defined in `docker-compose.yml`). For local overrides,
copy `.env.example` to `.env` and edit.

| Variable        | Default                                                       | Purpose                                                                   |
|-----------------|---------------------------------------------------------------|---------------------------------------------------------------------------|
| `DATABASE_URL`  | `postgresql+asyncpg://postgres:postgres@db:5432/containernet`  | SQLAlchemy async URL                                                      |
| `DOCKER_HOST`   | `unix:///var/run/docker.sock`                                 | Where the backend reaches the Docker daemon                               |
| `ADMIN_TOKEN`   | *(unset)*                                                     | Token required for `/api/admin/*`. **Leave unset in production** to disable those endpoints entirely (each request returns 403). |

The frontend picks up only its API base URL via the Nginx config;
it defaults to `http://localhost:8000`.

---

## Operating the stack

Use the Makefile:

```bash
make up        # docker compose up -d --build
make down      # docker compose down
make logs      # docker compose logs -f --tail=100
make test      # backend + frontend tests
make clean     # wipe containers + networks; start fresh
```

Common manual commands:

```bash
# Tail backend logs
docker logs -f containernet_backend

# Restart just the backend after editing Python source
# (./backend/app is bind-mounted into the container)
docker compose restart backend

# Rebuild + restart after a dependency change
docker compose up -d --build <service>

# Wipe everything and start fresh
docker compose down -v && docker compose up -d --build
```

### Backup and restore

The only stateful service is Postgres. To back up:

```bash
docker exec containernet_db pg_dump -U postgres containernet > backup.sql
docker exec -i containernet_db psql -U postgres containernet < backup.sql
```

The running Docker containers and bridges are **not** included in
the dump — those are recoverable by re-creating the projects
through the UI.

---

## Development

### Local frontend iteration

The frontend is built once and served as static files through
Nginx, so local changes need a rebuild:

```bash
docker compose build frontend && docker compose up -d frontend
```

There's no hot-reload container by default. For tight iteration
loops, mount the source and run `npm run dev` against a local
Node install:

```bash
cd frontend
npm install
npm run dev          # serves on http://localhost:5173 with /api proxied
```

### Local backend iteration

`./backend/app` is bind-mounted into the running container, so
edits to Python files take effect after:

```bash
docker compose restart backend
```

`./host-agent` and `./router-agent` are similarly bind-mounted
into the spawned containers — agent changes need a new container
spawn (i.e. restart the project), not a backend restart.

### End-to-end tests

The `tests/manual/` folder has standalone Python scripts that
exercise the full stack over HTTP. With the stack up:

```bash
python3 tests/manual/test_killer_demo.py
python3 tests/manual/test_logs.py
```

---

## Adding features

A few common patterns:

### Add a new attack mode

1. Add the mode string to `ATTACK_MODES` in
   `backend/app/models/project_node.py`.
2. Add the engine loop to
   `host-agent/attack_engine.py`.
3. Add the detector signal to
   `backend/app/services/attack_detector.py` (one new
   threshold + one check in `_poll_once`).
4. Add a teaching card in
   `frontend/src/attacks/lessons/<mode>.md`.
5. Add a button in
   `frontend/src/attacks/AttackerPanel.tsx`.

### Add a new node kind

The kinds are an enum (`backend/app/models/project_node.py`).
The corresponding logic lives in:
- `node_service.spawn_node` (container image + env vars + ports)
- `host-agent/agent.py` or `router-agent/agent.py` (role-specific
  HTTP API)
- `frontend/src/components/icons/NodeIcon.tsx` (visual)

### Extend the design system

Add the token to `phases/milestone-4/design-system.md` first,
then to `frontend/tailwind.config.js`, then use it. **Never the
other way around.**

---

## Security notes

The `backend` container is privileged against
`/var/run/docker.sock` — this is **root-equivalent** for the
Docker daemon. For a production deployment:

- Swap the bind mount for a TCP socket proxy (e.g.
  [Tecnativa docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy))
  and expose only the operations you need
- Set `ADMIN_TOKEN` (or leave it **unset** to disable
  `/api/admin/*` entirely)
- Place the stack behind a TLS-terminating reverse proxy
  (Caddy, Traefik, Nginx)
- Run the database on a separate host with a strong password

For an academic project on a single VM the defaults are fine;
document the implication in any deployment notes.

---

## Contributing

- Read [`architecture.md`](./architecture.md) for how the system
  fits together.
- Read [`phases/milestone-4/overview.md`](./phases/milestone-4/overview.md)
  for the current build plan.
- Read [`RUNBOOK.md`](./RUNBOOK.md) for the on-call contributor
  runbook (debugging, common failures, how the orphan sweeper
  works, etc.).
- The design system contract is
  [`phases/milestone-4/design-system.md`](./phases/milestone-4/design-system.md).
  Every UI change must respect it.

---

## Credits

ContainerNet is built as a foundation for a future Virtual Cyber
Range. It was inspired by:

- [Cisco Packet Tracer](https://www.netacad.com/courses/packet-tracer) —
  the original blank-canvas network simulator
- [Kathara Framework](https://github.com/KatharaFramework/Kathara) —
  container-per-host network emulation
- [Containerlab](https://github.com/srl-labs/containerlab) —
  declarative topology descriptions
- [Wireshark](https://www.wireshark.org/) — the protocol colour
  discipline that drives our design system

Built with:
[FastAPI](https://fastapi.tiangolo.com/) ·
[SQLAlchemy](https://www.sqlalchemy.org/) ·
[React Flow](https://reactflow.dev/) ·
[Zustand](https://github.com/pmndrs/zustand) ·
[Tailwind](https://tailwindcss.com/) ·
[Docker SDK for Python](https://docker-py.readthedocs.io/)
