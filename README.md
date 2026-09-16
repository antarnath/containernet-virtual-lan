# ContainerNet

> **A self-service, user-configurable virtual LAN platform.**
> Build, visualize, and simulate real Docker-based networks from your browser.

ContainerNet turns a one-line form (`Mesh · 8 hosts · auto subnet`) into a fully
running set of Linux containers wired together on a private bridge network.
No code, no YAML, no `docker exec` — pick a topology, click **Start**, and
inspect the result.

Everything is real: every host is a Docker container on its own per-project
bridge, every "communication" is an actual HTTP request that crosses the
topology, every status LED is a live heartbeat from a running process.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Layout](#project-layout)
- [Configuration](#configuration)
- [Operating the Stack](#operating-the-stack)
- [Development](#development)
- [Security Notes](#security-notes)
- [Credits](#credits)

---

## Features

ContainerNet ships six concrete capabilities. Every one runs against live
containers — there is no "demo mode".

| # | Capability              | Where                            | What it does                                                              |
|---|-------------------------|----------------------------------|---------------------------------------------------------------------------|
| 1 | **Create a LAN**        | `/builder`                       | Pick topology + host count → backend generates the graph and provisions a private bridge |
| 2 | **Visualize topology**  | `/projects/:id/topology`         | Interactive node-edge graph (React Flow) with drag-and-drop persistence    |
| 3 | **Start / stop hosts**  | `/projects/:id/hosts`            | One button per project; per-host LEDs reflect live heartbeats              |
| 4 | **Send a real request** | `/projects/:id/communications`   | Node-RED-style trigger panel: source, dest, protocol, payload              |
| 5 | **Watch packets**       | same page                        | Animated edges while the request is in flight                             |
| 6 | **Read message logs**   | `/projects/:id/messages`         | One Node-RED-style console per host with live message streams              |

### Supported topologies

Five shapes are available on the **LAN Builder** page:

| Topology | Description                                                            |
|----------|------------------------------------------------------------------------|
| **Mesh** | Every node connected to every other                                    |
| **Star** | One centre node connected to all satellites                            |
| **Ring** | Closed loop (`host-1` → `host-2` → … → `host-1`)                       |
| **Bus**  | Linear chain (`host-1` → `host-2` → … → `host-N`)                      |
| **Tree** | Balanced binary tree rooted at `host-1`                                |

Each shape places nodes with sensible default positions; drag them around to
suit your taste — positions are persisted to the database.

### Multi-project coexistence

Every project owns its own Docker bridge (named `proj_<uuid>_lan`) so two
projects can never see each other's traffic. Subnets are auto-assigned from
`10.30.0.0/24` … `10.99.0.0/24` — the only field you usually need to fill in
is the project name. Manual subnets are still supported; collisions return a
clear `409` rather than silently overlapping.

---

## Quick Start

### Prerequisites

- **Docker Engine 24+** with the socket accessible to your user
- **Docker Compose v2**
- **Node.js 20+** (only for local frontend builds — the image is self-contained)

### Launch

```bash
docker compose up -d --build
```

Then open:

| Surface      | URL                          |
|--------------|------------------------------|
| Web UI       | <http://localhost:5173>      |
| REST API     | <http://localhost:8000>      |
| Swagger docs | <http://localhost:8000/docs> |

The first build takes a few minutes (the `host-base` image is compiled from
source). Subsequent starts take seconds.

### Tear down

```bash
docker compose down        # stop everything, keep data
docker compose down -v     # stop AND wipe the database
```

---

## How It Works

A project's life cycle, end-to-end:

1. **You fill the form.** Topology type, host count, project name. Subnet
   is auto-assigned unless you toggle it off.

2. **Backend persists the graph.** A `Project` row is created along with one
   `ProjectHost` per node and one `ProjectEdge` per link. Each host's IP is
   pre-allocated inside the project's `/24`.

3. **You click Start.** The backend talks to the Docker daemon over the
   mounted Unix socket. It creates the bridge network, spawns one
   `containernet-host-base` container per host, attaches each to the bridge
   with the pinned IP, and attaches it to the backend's network so it can
   report in. Container IDs flow back into the DB.

4. **Hosts heartbeat.** Every spawned host runs a Python agent that POSTs
   `/api/hosts/{id}/heartbeat` every few seconds with its CPU, RAM, and
   network counters. A background sweeper on the backend flips hosts to
   `offline` after 15 s of silence.

5. **You trigger a communication.** The frontend posts a real HTTP request
   to `POST /api/projects/:id/communications`. The backend picks the source
   container's bridge IP, sends the request through the project's network,
   and records the latency, status, and full envelope. The frontend animates
   the edge while the request is in flight.

6. **You read messages.** Each host's agent also forwards per-host
   messages (`POST /api/projects/:id/messages`) which the frontend renders
   inside a Node-RED-style console window per host.

---

## Architecture

```
User (browser)
    │ HTTP / WebSocket
    ▼
React dashboard (Vite + TypeScript + React Flow + Zustand)
    │ REST + WS (per-project subscribe envelope)
    ▼
FastAPI backend (Python + SQLAlchemy + asyncpg)
    ├── Project / ProjectHost / ProjectEdge models
    ├── Topology generator (mesh / star / ring / bus / tree)
    ├── Container service (Docker SDK)
    ├── Network service (per-project bridge)
    ├── Communication orchestrator (HTTP via project bridge)
    ├── WebSocket broadcaster (per-project subscriptions)
    └── Host-agent runtime (spawned inside each container)
            │
            ├──► PostgreSQL (projects, hosts, edges, comms, messages)
            └──► Docker daemon (/var/run/docker.sock)
                       │
                       ▼
                One bridge per project:
                  proj_<uuid>_lan   ── isolated /24, only this project's hosts
                  containernet_lan  ── shared with the backend (heartbeats)
```

### Data model

| Table            | Rows                    | Notes                                                              |
|------------------|-------------------------|--------------------------------------------------------------------|
| `projects`       | One per project         | Status: `draft`, `running`, `partial`, `stopped`                   |
| `project_hosts` | One per host           | Position, IP, container_id, last heartbeat                          |
| `project_edges` | One per topology link  | Undirected (canonical ordering)                                     |
| `communications`| One per triggered send | Source/dest host IDs, latency, status                               |
| `messages`      | One per host-agent msg | Used by per-host message consoles                                   |

---

## Tech Stack

| Layer        | Tools                                                                            |
|--------------|----------------------------------------------------------------------------------|
| Frontend     | React 18, TypeScript, Vite, Tailwind, Zustand, React Flow, Axios. Static bundle served by Nginx. |
| Backend      | FastAPI, SQLAlchemy 2.0 (async), asyncpg, httpx, Docker SDK for Python, WebSockets. Lifespan hook handles graceful shutdown of spawned containers. |
| Database     | PostgreSQL 15.                                                                    |
| Hosts        | Python 3.11 (aiohttp, psutil, prometheus-client) running inside Alpine containers built from `infra/hosts/host-base.Dockerfile`. |
| Orchestration| Docker Compose v2.                                                                |

---

## Project Layout

```
ContainerNet/
├── backend/                       # FastAPI app
│   ├── app/
│   │   ├── main.py                # FastAPI app + lifecycle hooks
│   │   ├── core/                  # docker_client, db session, settings
│   │   ├── api/                   # HTTP route modules (one per resource)
│   │   ├── ws/                    # WebSocket connection manager + envelopes
│   │   ├── schemas/               # Pydantic request/response models
│   │   ├── models/                # SQLAlchemy ORM models
│   │   └── services/              # Domain logic (projects, containers, networks, …)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── wait-for-db.sh
├── frontend/                      # React + Vite dashboard
│   ├── src/
│   │   ├── api/                   # Typed REST client
│   │   ├── store/                 # Zustand stores (per resource)
│   │   ├── hooks/                 # useWebSocket + cross-cutting hooks
│   │   ├── pages/                 # Top-level routed views
│   │   ├── components/            # Reusable UI (topology, hosts, trigger, …)
│   │   ├── utils/                 # Topology icons + descriptions
│   │   └── types/                 # Shared TS interfaces
│   ├── Dockerfile                 # Multi-stage build → Nginx static bundle
│   ├── nginx.conf                 # /api and /ws proxy to backend
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── package.json
├── host-agent/                    # Python agent running inside every spawned host
│   ├── agent.py                   # Entrypoint: starts metrics + message + heartbeat
│   ├── config.py                  # Reads HOST_ID / HOST_IP / PROJECT_ID env
│   ├── metrics_exporter.py        # /healthz + Prometheus /metrics on :9100
│   ├── message_service.py         # /send + /receive on :8080 (HTTP-based "ping")
│   ├── message_reporter.py        # Fire-and-forget reporter to backend
│   ├── health_monitor.py          # Periodic /api/health POSTs
│   └── requirements.txt
├── infra/
│   └── hosts/
│       └── host-base.Dockerfile   # Alpine + Python base used for every spawned host
├── scripts/
│   └── smoke_test.sh              # End-to-end curl-based smoke test (Phases 0 → 9)
├── docker-compose.yml             # db + backend + host-base + frontend
├── .env.example                   # Sample environment variables
└── README.md                      # You are here
```

---

## Configuration

All configuration is via environment variables on the `backend` service (defined
in `docker-compose.yml`). For local overrides, copy `.env.example` to `.env` and
edit.

| Variable        | Default                                                       | Purpose                                                                   |
|-----------------|---------------------------------------------------------------|---------------------------------------------------------------------------|
| `DATABASE_URL`  | `postgresql+asyncpg://postgres:postgres@db:5432/containernet`  | SQLAlchemy async URL                                                      |
| `DOCKER_HOST`   | `unix:///var/run/docker.sock`                                 | Where the backend reaches the Docker daemon                               |
| `ADMIN_TOKEN`   | *(unset)*                                                     | Token required for `/api/admin/*`. **Leave unset in production** to disable those endpoints entirely (each request returns 403). |

The frontend picks up only its API base URL via the Nginx config; it defaults
to `http://localhost:8000`.

---

## Operating the Stack

### Common commands

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

> The running Docker containers and bridges are **not** included in the dump —
> those are recoverable by re-creating the projects through the UI.

### Smoke test

With the stack up, run the end-to-end smoke test:

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
```

It exercises the public REST surface and exits non-zero on the first failure.

---

## Development

### Local frontend iteration

The frontend is built once and served as static files through Nginx, so local
changes need a rebuild:

```bash
docker compose build frontend && docker compose up -d frontend
```

There's no hot-reload container by default. For tight iteration loops, mount
the source and run `npm run dev` against a local Node install:

```bash
cd frontend
npm install
npm run dev          # serves on http://localhost:5173 with /api proxied
```

### Local backend iteration

`./backend/app` is bind-mounted read-only into the running container, so edits
to Python files take effect after:

```bash
docker compose restart backend
```

`./host-agent` is similarly bind-mounted into the `host-base` image and into
spawned host containers.

### Adding a topology template

1. Add a generator function in `backend/app/services/topology_generator.py`
2. Register it in the `layout_fns` / `edge_fns` maps
3. Add the type literal in `backend/app/schemas/project.py`
4. Add an icon + label in `frontend/src/utils/topologyIcons.tsx`

### Adding a new resource

1. Pydantic schemas in `backend/app/schemas/`
2. ORM model in `backend/app/models/`
3. Service module in `backend/app/services/`
4. Router in `backend/app/api/` + `include_router` in `backend/app/api/__init__.py`
5. Typed client in `frontend/src/api/client.ts`
6. Zustand store in `frontend/src/store/`
7. Page component in `frontend/src/pages/`

---

## Security Notes

The `backend` container is privileged against `/var/run/docker.sock` — this is
**root-equivalent** for the Docker daemon. For a production deployment:

- Swap the bind mount for a TCP socket proxy (e.g.
  [Tecnativa docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy))
  and expose only the operations you need
- Set `ADMIN_TOKEN` (or leave it **unset** to disable `/api/admin/*` entirely)
- Place the stack behind a TLS-terminating reverse proxy (Caddy, Traefik, Nginx)
- Run the database on a separate host with a strong password

For an academic project on a single VM the defaults are fine; document the
implication in any deployment notes.

---

## Credits

ContainerNet is built as a foundation for a future Virtual Cyber Range. It was
inspired by:

- [Kathara Framework](https://github.com/KatharaFramework/Kathara) —
  container-per-host network emulation
- [Containerlab](https://github.com/srl-labs/containerlab) —
  declarative topology descriptions
- [Node-RED](https://nodered.org/) — trigger/output console paradigm
- [OpenCyberRange](https://opencyberrange.com/) — cyber-range orchestration ideas

Built with:
[FastAPI](https://fastapi.tiangolo.com/) ·
[SQLAlchemy](https://www.sqlalchemy.org/) ·
[React Flow](https://reactflow.dev/) ·
[Zustand](https://github.com/pmndrs/zustand) ·
[Tailwind](https://tailwindcss.com/) ·
[Docker SDK for Python](https://docker-py.readthedocs.io/)