# ContainerNet

> **A self-service, user-configurable virtual LAN platform.**
> Build, visualize, and simulate real Docker-based networks from your browser.

ContainerNet is a web platform that turns the **six professor requirements** into a user-driven experience:

1. **Monitor hosts** — real-time per-host status, CPU, RAM, network
2. **Visualize network topology** — interactive graph with drag-and-drop persistence
3. **Simulate host-to-host communication** — Node-RED-style trigger panel
4. **Show real-time data flow** — animated packets on topology edges
5. **Display messages between hosts** — per-host console windows
6. **Container-based virtual LAN** — every host is a real Docker container

…except now **the user** picks the topology (mesh / star / ring / bus / tree), the host count (3–32), and the subnet — and the backend builds that exact LAN on demand.

---

## 🚀 Quick Start

```bash
docker compose up -d --build
```

Then open:

- **Frontend dashboard**: `http://localhost:5173`
- **Backend API**: `http://localhost:8000`
- **API docs (Swagger)**: `http://localhost:8000/docs`

You'll land on the **LAN Builder**. Pick a topology, name your project, choose how many hosts, hit Create — and the backend spawns that LAN as real Docker containers on a fresh per-project bridge network.

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| **[overview.md](overview.md)** | Full project specification (architecture, data flows, schema, API, 5 topology templates) |
| **[phases/README.md](phases/README.md)** | Build roadmap — 9 phases; the dynamic MVP is feature-complete |
| **[phases/phase_00..09_*.md](phases/)** | Step-by-step guides for every phase |
| **Swagger UI** | `http://localhost:8000/docs` — every REST endpoint annotated |
| **WebSocket** | `/ws` — per-project event stream (subscribe envelope, message events) |

Start with `overview.md` for the big picture, then follow the phases in order.

## 🧩 What's Inside

The platform ships with these user-facing surfaces:

- **Dashboard** (`/`) — platform-wide totals + recent-activity feed (Phase 09)
- **LAN Builder** (`/builder`) — pick topology, host count, subnet (Phase 04)
- **Projects** (`/projects`) — grid of all projects with Start / Stop / Delete (Phase 04, polished Phase 09)
- **Per-project Topology** (`/projects/:id/topology`) — interactive React Flow view with drag-persist (Phase 04)
- **Per-project Hosts** (`/projects/:id/hosts`) — status LEDs + live metrics (Phase 05)
- **Per-project Communications** (`/projects/:id/communications`) — Node-RED-style trigger + log (Phase 06)
- **Per-project Messages** (`/projects/:id/messages`) — one console per host, real-time bubbles (Phase 08)

---

## 🏗️ Architecture

```
User (browser)
    │ HTTP / WebSocket
    ▼
React Dashboard (Vite + TypeScript + React Flow + Zustand)
    │ REST / WS
    ▼
FastAPI Backend (Python + SQLAlchemy + asyncpg)
    ├── Project / ProjectHost / ProjectEdge models
    ├── Topology generator (mesh / star / ring / bus / tree)
    ├── Container service (Docker SDK)
    ├── Network service (per-project bridge)
    ├── Communication orchestrator
    └── WebSocket broadcaster (per-project subscriptions)
    │
    ├──► PostgreSQL (projects, hosts, edges, comms, messages)
    └──► Docker daemon (/var/run/docker.sock)
            │
            ▼
      One bridge per project:
        proj_<uuid_A>_lan (10.20.0.0/24)  ── Lab A: 5 hosts in mesh
        proj_<uuid_B>_lan (10.30.0.0/24)  ── Lab B: 8 hosts in star
        proj_<uuid_C>_lan (10.40.0.0/24)  ── Lab C: 12 hosts in ring
```

---

## 🔧 Tech

- **Frontend**: React 18, TypeScript, Vite, Tailwind, Zustand, React Flow, Dagre, Axios
- **Backend**: FastAPI, SQLAlchemy 2.0 async, asyncpg, httpx, Docker SDK for Python
- **Data**: PostgreSQL 15
- **Hosts**: Python 3.11 (aiohttp, psutil, prometheus-client) running inside Alpine containers
- **Infra**: Docker 24+, Docker Compose v2

---

## 📜 License & Credits

Academic project. Inspired by:

- [Kathara Framework](https://github.com/KatharaFramework/Kathara)
- [Containerlab](https://github.com/srl-labs/containerlab)
- [Node-RED](https://nodered.org/)
- [OpenCyberRange](https://opencyberrange.com/)

Built as the foundation for a future Virtual Cyber Range.