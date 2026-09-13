# ContainerNet — Project Overview

> **A Self-Service, User-Configurable Virtual LAN Platform — Build, Visualize, and Simulate Real Docker-Based Networks from Your Browser**

---

## 1. Project Title

**ContainerNet: A Web-Based Self-Service Platform for Building, Visualizing, and Simulating User-Defined Virtual LANs on Container Infrastructure**

---

## 2. Project Vision (As Directed by Project Guide)

> *"We need to monitor hosts, visualize network topology, simulate host-to-host communication, show real-time data flow, and display messages between hosts — where every host is a single container. This is the foundation for our future target: a **Virtual Cyber Lab**."*
>
> **Project Guide, Department of Computer Science**

The original ContainerNet prototype demonstrated these capabilities with a **fixed three-host LAN** (`pc1`, `pc2`, `pc3`) baked into Docker Compose. That demo satisfied the six core requirements — but it was a demo, not a tool.

**This evolved version** turns ContainerNet into a **self-service platform**. A user opens the dashboard, fills out a short form — *name, topology type, host count, subnet* — and the backend **instantly creates that exact LAN** as real Docker containers. The user can then drag hosts anywhere on the topology canvas (positions persist), trigger messages between any two hosts, watch animated packets flow over edges in real time, and read live message consoles per host. Save the project, close the browser, come back tomorrow — the LAN and the layout are exactly where you left them.

The six core requirements are still the success criteria. What changes is **who controls the network**: not the developer in `docker-compose.yml`, but **the user in the browser**.

### 2.1 Six Core Requirements (from Project Guide)

| # | Requirement | How ContainerNet Delivers It (Dynamic Edition) |
|---|-------------|-------------------------------------------------|
| 1 | **Monitor Hosts** | User creates a project with N hosts → backend spawns N containers → each container reports heartbeats, CPU, RAM, network. Dashboard shows per-host status LEDs. |
| 2 | **Visualize Network Topology** | User picks **Mesh / Star / Ring / Bus / Tree** with any host count → React Flow renders it. Drag hosts anywhere; positions persist. |
| 3 | **Simulate Host-to-Host Communication** | Within any project, pick any two hosts → trigger HTTP/TCP message → orchestrator dispatches it across the project's real bridge network. |
| 4 | **Show Real-time Data Flow** | WebSocket pushes per-project events. Animated edges light up green on every in-flight message. Multi-project clients don't bleed into each other. |
| 5 | **Display Messages Between Hosts** | Every host has its own Node-RED-style message console. Outgoing in blue, incoming in green, real-time. Works for any number of hosts. |
| 6 | **Container-based Virtual LAN** | Each host is a real Docker container on a **per-project** bridge network (`proj_<uuid>_lan`, user-defined subnet). Truly isolated LANs. |

---

## 3. Why "Dynamic"?

The original static demo (`pc1` / `pc2` / `pc3` hardcoded in `docker-compose.yml`) proved the concept. But to be a **platform**, ContainerNet must answer the question: *"What if I want 8 hosts in a ring?"* — without anyone editing YAML, rebuilding images, or restarting the stack.

Dynamic ContainerNet lets a user:

| Capability | Before (Static) | Now (Dynamic) |
|------------|-----------------|---------------|
| Change host count | Edit `docker-compose.yml`, rebuild, restart | Move a slider, click Create |
| Change topology | Rebuild the entire stack | Pick from 5 templates in a dropdown |
| Run multiple LANs simultaneously | Impossible (one shared `containernet_lan`) | Yes — each project gets its own bridge |
| Persist between sessions | Only via DB (no topology state) | Topology, hosts, edges, drag positions all persisted |
| Add a new project type later | Touch code, add files | Add one function to `topology_generator.py` |
| Democratize the platform | Devs only | Anyone with a browser |

---

## 4. Inspiration & References

| Reference | What We Borrow |
|-----------|----------------|
| **[Kathara Framework](https://github.com/KatharaFramework/Kathara)** | Lightweight container-based network emulation — each "router/host" is a container on a shared bridge. ContainerNet does the same, but spawns those containers **on demand from a web UI**. |
| **[Containerlab](https://github.com/srl-labs/containerlab)** | Declarative topology definitions. ContainerNet implements this declaratively **at runtime** — the topology definition lives in `topology_generator.py` and the database, not in a YAML file the user maintains. |
| **[OpenCyberRange](https://opencyberrange.com/)** | Cyber range architecture — multi-host virtual lab with web control plane. This is the long-term target. |
| **[PeerJ CS-1574](https://peerj.com/articles/cs-1574/)** | Academic foundation for cyber range design and learning. |
| **[Node-RED](https://nodered.org/)** | Visual flow programming — drag nodes, wire them, see live output in a debug panel. ContainerNet's **Trigger Panel + Per-Host Message Windows** are directly inspired by this. |
| **[awesome-vulnerable](https://github.com/kaiiyer/awesome-vulnerable)** | Future target: deploy vulnerable training apps inside the user-created LAN. |
| **ContainerFlow & Atlas** | Reference dashboards for visualizing host/container topology. |

Our approach: **borrow Kathara's container-per-host philosophy**, **Containerlab's declarative topology** (made user-facing), and **Node-RED's flow-output paradigm**, then add a **self-service web UI** on top.

---

## 5. Problem Statement

Traditional network monitoring tools (Grafana, Prometheus, Portainer, Zabbix) provide **resource-level metrics** and **container management**, but they **do not visualize real-time communication between hosts** in a user-defined LAN.

Existing container-lab tools (Kathara, Containerlab) are excellent for **emulating networks** but:
- They require CLI or YAML editing for every topology change.
- They lack a **rich, web-based real-time visualization layer** showing which host is talking to which, what payload, with what latency.
- They don't have a Node-RED style **debug/output window** showing live messages per host.
- They don't let you **save a project** (named topology + hosts + edges + positions) and reload it later.

ContainerNet fills this gap: a **self-service web platform** that builds real Docker-based LANs on demand, visualizes them interactively, simulates host-to-host traffic, animates packets in real time, and streams per-host messages — all from the browser.

---

## 6. Goals & Objectives

### 6.1 Primary Goals (Phase 1 — Foundations)

1. **Self-Service LAN Builder** — A user fills out a form (name, topology, host count, subnet) and the backend builds the LAN as real Docker containers.
2. **Five Topology Templates** — Mesh, Star, Ring, Bus (linear), Tree. Each is a pure function in `topology_generator.py`.
3. **Persistent Projects** — Topology, host records, edges, and node positions live in the database. Reload any project tomorrow and it's exactly as you left it.
4. **Free Drag-and-Drop** — The topology view lets users drag nodes anywhere. Positions persist via `PATCH /api/projects/{id}/nodes/{host_id}`.
5. **Real-Time Updates** — WebSocket pushes host status and in-flight communication events per project.
6. **Per-Host Message Windows** — Node-RED-style debug panes, scoped per project, updated in real time.
7. **Multiple Coexisting Projects** — Each project runs in its own Docker bridge network. Different projects cannot interfere.

### 6.2 Future Goals (Phase 2+ — Virtual Cyber Lab)

- Deploy vulnerable services (DVWA, Metasploitable-like apps) inside any user-created project.
- Simulate attacks/defenses between hosts in a project.
- Capture and visualize attack flows on the same dashboard.
- Multi-user lab sessions with isolated topologies.
- Export/Import projects as YAML (Containerlab compatibility).

---

## 7. Core Concepts

### 7.1 Project = One User-Defined LAN

The unit of work in dynamic ContainerNet is a **project**. A project is a row in the `projects` table that owns:
- A name (e.g., *"Lab A - 5 host mesh"*)
- A topology type (`mesh`, `star`, `ring`, `bus`, `tree`)
- A host count (any positive integer, typically 3–32)
- A subnet (e.g., `10.20.0.0/24`)
- A status (`created` → `running` → `stopped` → `deleted`)
- A collection of hosts, edges, and saved positions

```
Project: "Lab A"
├── topology:   mesh
├── hosts:      5
├── subnet:     10.20.0.0/24
├── bridge:     proj_<uuid>_lan
├── hosts:
│   ├── pc1  10.20.0.11  position(120, 200)
│   ├── pc2  10.20.0.12  position(380,  80)
│   ├── pc3  10.20.0.13  position(380, 320)
│   ├── pc4  10.20.0.14  position(640, 200)
│   └── pc5  10.20.0.15  position(900, 200)
└── edges:
    ├── pc1 ↔ pc2, pc1 ↔ pc3, pc1 ↔ pc4, pc1 ↔ pc5
    ├── pc2 ↔ pc3, pc2 ↔ pc4, pc2 ↔ pc5
    ├── pc3 ↔ pc4, pc3 ↔ pc5
    └── pc4 ↔ pc5
```

### 7.2 Every Host is a Container — Still

Following the **Kathara / Containerlab model**, every "PC" in a project is a single Docker container. The difference is **who creates them**: the backend (via Docker SDK), on user request, instead of `docker-compose up`.

```
pc1 ──►  container: pc-<proj-uuid>-1   (IP: 10.20.0.11)
pc2 ──►  container: pc-<proj-uuid>-2   (IP: 10.20.0.12)
...
```

All containers in a project are attached to the **project's bridge** (`proj_<uuid>_lan`, user-defined subnet) — that *is* the virtual LAN for that project.

### 7.3 Host Agent (Runs Inside Each Container)

Unchanged from the static version. Each dynamically-spawned host container runs the same Python Host Agent:

```
Host Agent
├── 1. Health Monitor      → POST heartbeat to backend every 5s (with project_id)
├── 2. Metrics Exporter    → /metrics on :9100 (Prometheus format)
├── 3. Message Receiver    → /receive on :8080
└── 4. Message Sender      → Outbound /send to peers
```

The backend passes `PROJECT_ID`, `HOST_ID`, `HOST_NAME`, `HOST_IP`, `BACKEND_URL` as environment variables when spawning each container.

### 7.4 Communication Paradigm (Node-RED Inspired)

Inside any project, the dashboard exposes a **flow-based interface**:

- **Trigger** — User picks a source host and a destination host (within the active project).
- **Action** — User defines a payload and protocol (HTTP/TCP).
- **Execute** — Backend orchestrator dispatches the message across the project's bridge.
- **Output** — Live message appears in:
  - Source host's output window (sent)
  - Destination host's output window (received)
  - The animated topology edge (data in transit)
  - The project's communication log

This is identical to the static demo's paradigm — but now scoped per project and against any user-defined topology.

### 7.5 Five Topology Templates

`topology_generator.py` exposes five pure functions. Each takes a host count (and optionally a project metadata) and returns `{nodes, edges}`:

| Topology | Generator Function | Edges (n = host count) | Visual |
|----------|--------------------|------------------------|--------|
| **Mesh** | `generate_mesh(n)` | n·(n−1)/2 | Every host connects to every other host |
| **Star** | `generate_star(n)` | n−1 | One central hub, all others connect to it |
| **Ring** | `generate_ring(n)` | n | Each host connects to its two neighbors; last connects to first |
| **Bus / Linear** | `generate_bus(n)` | n−1 | Chain: h1—h2—h3—…—hN |
| **Tree** | `generate_tree(n)` | n−1 | Balanced binary tree (or k-ary tree if you choose) |

Adding a new topology (say, "Hypercube" or "Torus") is a single new function.

---

## 8. High-Level Architecture

```
                            ┌──────────────────────────────┐
                            │             USER             │
                            └──────────────┬───────────────┘
                                           │ Browser
                                           ▼
                ┌────────────────────────────────────────────────────┐
                │           REACT DASHBOARD (Web UI)                 │
                │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
                │ │ LAN Builder  │ │  Projects    │ │  Topology    │ │
                │ │  (form)      │ │  (list)      │ │  (drag-drop) │ │
                │ └──────────────┘ └──────────────┘ └──────────────┘ │
                │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
                │ │  Hosts       │ │  Comm Log    │ │  Messages    │ │
                │ │  (per proj)  │ │  (per proj)  │ │  (per host)  │ │
                │ └──────────────┘ └──────────────┘ └──────────────┘ │
                └────────────────────────┬───────────────────────────┘
                                         │ REST API + WebSocket
                                         ▼
                ┌────────────────────────────────────────────────────┐
                │       FASTAPI BACKEND (Control Plane + Docker)     │
                │ ┌────────────────┐ ┌─────────────────────────────┐ │
                │ │ Project Service│ │  Container Service          │ │
                │ │ (CRUD, layout) │ │  (spawn/stop/remove via     │ │
                │ │                │ │   Docker SDK)               │ │
                │ └────────────────┘ └─────────────────────────────┘ │
                │ ┌────────────────┐ ┌─────────────────────────────┐ │
                │ │ Network Service│ │  Communication Orchestrator │ │
                │ │ (per-proj      │ │  (HTTP /send ↔ /receive)    │ │
                │ │  bridge nets)  │ │                             │ │
                │ └────────────────┘ └─────────────────────────────┘ │
                │ ┌────────────────┐ ┌─────────────────────────────┐ │
                │ │ Topology Gen.  │ │  WebSocket Broadcaster      │ │
                │ │ (5 templates)  │ │  (per-project channels)     │ │
                │ └────────────────┘ └─────────────────────────────┘ │
                └────┬──────────────────┬──────────────────┬─────────┘
                     │                  │                  │
                     ▼                  ▼                  ▼
              ┌───────────┐       ┌───────────┐       ┌───────────┐
              │PostgreSQL │       │   Redis   │       │ Docker    │
              │(projects, │       │ (Pub/Sub, │       │ Socket    │
              │ hosts,    │       │  cache)   │       │ /var/run/ │
              │ edges)    │       │           │       │ docker.   │
              └───────────┘       └───────────┘       │ sock      │
                                                     └─────┬─────┘
                                                           │
                                       ┌───────────────────┴───────────────────┐
                                       │                                       │
                                       ▼                                       ▼
                          ┌─────────────────────────┐            ┌─────────────────────────┐
                          │  PROJECT A              │            │  PROJECT B              │
                          │  Bridge: proj_A_lan     │            │  Bridge: proj_B_lan     │
                          │  Subnet: 10.20.0.0/24   │            │  Subnet: 10.30.0.0/24   │
                          │  Topology: mesh, 5 hosts│            │  Topology: ring, 8 hosts│
                          │  ┌────┐ ┌────┐ ┌────┐   │            │  ┌────┐ ┌────┐ ┌────┐   │
                          │  │pc1 │═│pc2 │═│pc3 │   │            │  │pc1 │═│pc2 │═│pc3 │   │
                          │  └──┬─┘ └─┬──┘ └─┬──┘   │            │  └──┬─┘ └─┬──┘ └─┬──┘   │
                          │     ╲    ╱╲    ╱       │            │     ╲    ╱╲    ╱       │
                          │      ╲  ╱  ╲  ╱        │            │      ╲  ╱  ╲  ╱        │
                          │     ┌────┐ ┌────┐      │            │     ┌────┐ ┌────┐      │
                          │     │pc4 │═│pc5 │      │            │     │pc4 │═│pc5 │      │
                          │     └────┘ └────┘      │            │     └────┘ └────┘      │
                          │  All running on real   │            │  All running on real   │
                          │  Docker containers     │            │  Docker containers     │
                          └─────────────────────────┘            └─────────────────────────┘
```

---

## 9. Project Structure (Monorepo)

```
ContainerNet/
├── README.md
├── overview.md                      # ← This file (rewritten for dynamic edition)
├── docker-compose.yml               # Backend + DB + frontend only; host containers spawned dynamically
│
├── infra/
│   └── hosts/
│       └── host-base.Dockerfile     # Base image for every dynamic host (Python + aiohttp + psutil)
│
├── host-agent/                      # Python agent running INSIDE every spawned host container
│   ├── agent.py                     # Main entrypoint (reads PROJECT_ID from env)
│   ├── health_monitor.py            # POSTs heartbeat with project_id
│   ├── message_service.py           # /send and /receive endpoints
│   ├── metrics_exporter.py          # /metrics on :9100
│   ├── message_reporter.py          # POSTs message events back to backend
│   ├── config.py                    # Reads HOST_ID, HOST_NAME, HOST_IP, PROJECT_ID, BACKEND_URL
│   └── requirements.txt
│
├── backend/                         # FastAPI control plane + Docker orchestrator
│   ├── app/
│   │   ├── main.py                  # Lifespan: init DB, Docker client, sweeper
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic settings
│   │   │   ├── database.py          # Async SQLAlchemy engine
│   │   │   └── docker_client.py     # NEW: singleton Docker SDK wrapper
│   │   ├── models/
│   │   │   ├── project.py           # NEW: Project ORM
│   │   │   ├── project_host.py      # NEW: ProjectHost ORM (per-project host row)
│   │   │   ├── project_edge.py      # NEW: ProjectEdge ORM
│   │   │   ├── communication.py     # Extended with project_id FK
│   │   │   └── message.py           # NEW: Per-project message event log
│   │   ├── schemas/
│   │   │   ├── project.py           # NEW: Pydantic schemas
│   │   │   ├── heartbeat.py         # Extended with project_id
│   │   │   ├── communication.py
│   │   │   └── message.py
│   │   ├── services/
│   │   │   ├── container_service.py # NEW: spawn/stop/remove via Docker SDK
│   │   │   ├── network_service.py   # NEW: per-project bridge networks
│   │   │   ├── topology_generator.py# NEW: 5 pure functions for 5 topologies
│   │   │   ├── project_service.py   # NEW: project CRUD + lifecycle
│   │   │   ├── host_service.py      # Refactored: per-project upsert + sweep
│   │   │   ├── communication_service.py # Refactored: per-project dispatch
│   │   │   └── message_service.py   # NEW: per-project message ingest
│   │   ├── api/
│   │   │   ├── projects.py          # NEW: /api/projects CRUD + start/stop
│   │   │   ├── hosts.py             # Refactored: /api/projects/{id}/hosts
│   │   │   ├── communications.py    # Refactored: /api/projects/{id}/communications
│   │   │   ├── messages.py          # NEW: /api/projects/{id}/hosts/{host_id}/messages
│   │   │   ├── topology.py          # Per-project
│   │   │   ├── health.py            # Heartbeat ingest (project_id in payload)
│   │   │   └── websocket.py         # /ws with subscribe-to-project support
│   │   └── ws/
│   │       └── events.py            # Per-project envelopes + manager
│   ├── migrations/
│   ├── requirements.txt             # + docker (Docker SDK)
│   └── Dockerfile
│
├── frontend/                        # React dashboard (with LAN Builder)
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                  # Routes: /builder, /projects, /projects/:id/{topology,hosts,messages,...}
│   │   ├── api/
│   │   │   └── client.ts            # + ProjectsAPI
│   │   ├── pages/
│   │   │   ├── LANBuilderPage.tsx   # NEW: entry form
│   │   │   ├── ProjectsPage.tsx     # NEW: project cards grid
│   │   │   ├── Dashboard.tsx        # Multi-project overview
│   │   │   ├── TopologyPage.tsx     # /projects/:id/topology
│   │   │   ├── HostsPage.tsx        # /projects/:id/hosts
│   │   │   ├── CommunicationsPage.tsx# /projects/:id/communications
│   │   │   └── MessagesPage.tsx     # /projects/:id/messages
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx      # LAN Builder, Projects, current project switcher
│   │   │   │   └── Topbar.tsx
│   │   │   ├── topology/
│   │   │   │   ├── TopologyCanvas.tsx# NEW: React Flow + drag-persist
│   │   │   │   ├── TopologyView.tsx # Animated edges + drag-stop → PATCH
│   │   │   │   ├── HostNode.tsx     # Per-project LED
│   │   │   │   └── StatusLED.tsx
│   │   │   ├── host-monitor/
│   │   │   │   └── HostCard.tsx
│   │   │   ├── trigger/
│   │   │   │   ├── TriggerPanel.tsx # Reads hosts from active project
│   │   │   │   └── ProtocolSelector.tsx
│   │   │   ├── message-window/
│   │   │   │   ├── MessageWindow.tsx# Generic per-host console
│   │   │   │   └── MessageBubble.tsx
│   │   │   └── common/
│   │   │       └── ToastContainer.tsx
│   │   ├── store/                   # Zustand
│   │   │   ├── projectStore.ts      # NEW: current project + projects list
│   │   │   ├── hostStore.ts         # Keyed by project_id
│   │   │   ├── commStore.ts         # Keyed by project_id
│   │   │   ├── messageStore.ts      # Keyed by (project_id, host_id)
│   │   │   ├── realtimeStore.ts     # Keyed by project_id
│   │   │   └── toastStore.ts
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts      # Sends {type:"subscribe", project_id} on connect
│   │   ├── types/
│   │   │   └── index.ts             # Project, Topology, MessageEvent types
│   │   └── utils/
│   │       ├── layout.ts            # Dagre-based default layout
│   │       └── topologyIcons.ts     # NEW: SVG icons for 5 topologies
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── package.json
│
├── docs/
│   ├── architecture.md
│   ├── topology-templates.md        # How to add a new topology
│   ├── screenshots/
│
├── phases/                          # Internal dev roadmap (not pushed to git)
│   ├── README.md                    # Roadmap with current-state status table
│   ├── phase_00_project_reset.md            ✅ Complete
│   ├── phase_01_docker_orchestration.md     ✅ Complete
│   ├── phase_02_projects_and_topology_templates.md   ✅ Complete
│   ├── phase_03_dynamic_host_lifecycle.md   📋 Planned
│   ├── phase_04_dynamic_topology_visualization.md    📋 Planned
│   ├── phase_05_per_project_monitoring.md   📋 Planned
│   ├── phase_06_project_scoped_communication.md      📋 Planned
│   ├── phase_07_realtime_websocket.md       📋 Planned
│   ├── phase_08_message_windows.md          📋 Planned
│   └── phase_09_polish_and_docs.md          📋 Planned
│
└── scripts/
    ├── seed_hosts.py                # Legacy — kept only for migration
    ├── demo_traffic.py              # Generate sample traffic for demos
    └── cleanup_orphans.py           # NEW: remove orphan project containers/networks
```

---

## 10. LAN Design — Per-Project Isolation

In static ContainerNet, every PC was on the same bridge (`containernet_lan`). In dynamic ContainerNet, **each project gets its own bridge**:

```
Project A:
  Bridge:   proj_<uuid_A>_lan
  Subnet:   10.20.0.0/24
  Gateway:  10.20.0.1
  Hosts:    pc1..pc5 at 10.20.0.11..15

Project B:
  Bridge:   proj_<uuid_B>_lan
  Subnet:   10.30.0.0/24
  Gateway:  10.30.0.1
  Hosts:    pc1..pc8 at 10.30.0.11..18
```

Hosts in Project A **cannot** reach hosts in Project B without explicit bridging — the same isolation you'd expect from two physically separate switches.

### 10.1 IP Allocation

Deterministic and conflict-free: given a project with subnet `10.20.0.0/24` and host N, host i gets `10.20.0.{10+i}`. Hostnames are `pc1..pcN` within each project (uniqueness guaranteed by `(project_id, host_id)` composite keys in the DB).

### 10.2 Container Naming

Each dynamically-spawned container is named `pc-<project_short_id>-<n>` for easy CLI inspection:

```bash
$ docker ps
pc-a1b2c3-1   containernet-host-base:latest   python3 /app/host-agent/agent.py
pc-a1b2c3-2   containernet-host-base:latest   python3 /app/host-agent/agent.py
pc-d4e5f6-1   containernet-host-base:latest   python3 /app/host-agent/agent.py
```

---

## 11. Data Flow

### 11.1 LAN Creation Flow (New!)

```
[User on Dashboard]
    │  Opens LAN Builder page (/builder)
    │  Fills form:
    │    name:        "Lab A"
    │    topology:    "mesh"
    │    host_count:  5
    │    subnet:      "10.20.0.0/24"
    │  Clicks "Create & Start"
    ▼
[React → FastAPI: POST /api/projects]
    │
    ▼
[FastAPI Project Service]
    │  Validates inputs (host_count 3-32, subnet not in use)
    │  Generates topology: topology_generator.generate_mesh(5)
    │    → {nodes: 5, edges: 10}
    │  Allocates deterministic IPs: 10.20.0.11..15
    │  Inserts Project + ProjectHost + ProjectEdge rows
    │  Returns project_id
    │
    ▼
[POST /api/projects/{id}/start]  (automatic next step)
    │
    ▼
[Network Service]
    │  Creates bridge: proj_<uuid>_lan
    │    with subnet 10.20.0.0/24
    │
    ▼
[Container Service]
    │  For each ProjectHost row:
    │    docker.containers.run(
    │      image="containernet-host-base:latest",
    │      name="pc-<short>-<n>",
    │      network="proj_<uuid>_lan",
    │      ipv4_address="10.20.0.1X",
    │      environment={
    │        "PROJECT_ID": "<uuid>",
    │        "HOST_ID":    "pc<n>",
    │        "HOST_NAME":  "PC<n>",
    │        "HOST_IP":    "10.20.0.1X",
    │        "BACKEND_URL":"http://backend:8000"
    │      },
    │      volumes={"./host-agent": {"bind":"/app/host-agent","mode":"rw"}},
    │      command="python3 /app/host-agent/agent.py",
    │      detach=True
    │    )
    │  Updates ProjectHost.container_id for each row
    │
    ▼
[Each Host Container Starts]
    │  Host Agent reads env (PROJECT_ID, HOST_ID, etc.)
    │  Begins heartbeats (every 5s) including project_id
    │  Begins Prometheus-format /metrics on :9100
    │  Begins /send and /receive listeners on :8080
    │
    ▼
[Backend persists container_id for each host]
    │
    ▼
[React Router: redirect to /projects/<id>/topology]
    │  Renders 5 nodes connected in mesh layout
    │  Status LEDs turn green as heartbeats arrive
```

### 11.2 Host Monitoring Flow (per project)

```
[PC1 Container in Project A]
    │  Host Agent runs psutil.cpu_percent(), etc.
    │  POSTs every 5s to /api/health:
    │    {project_id: <uuid_A>, host_id: "pc1", host_name: "PC1", host_ip: "10.20.0.11"}
    ▼
[FastAPI health.py]
    │  upsert_heartbeat(session, hb)
    │  Finds row in project_hosts WHERE project_id = <uuid_A> AND host_id = "pc1"
    │  Updates status=ONLINE, last_seen=now()
    │
    ▼
[WebSocket broadcast: {type:"host_status_change", project_id, host_id, status:"online"}]
    │
    ▼
[React Dashboard subscribed to <uuid_A>]
    │  PC1's node LED turns green
    │  Hosts page counter updates
```

### 11.3 Communication Flow (per project)

```
[User in Project A opens Trigger Panel]
    │  Source = PC1, Destination = PC2, Payload = "Hello PC2"
    │  Clicks Send
    ▼
[React → POST /api/projects/<uuid_A>/communications]
    │
    ▼
[Communication Service]
    │  Validates both hosts belong to project <uuid_A>
    │  Creates Communication row, status=PENDING, project_id=<uuid_A>
    │  WebSocket: {type:"communication_start", project_id, id, source:"pc1", dest:"pc2"}
    │
    ▼
[POSTs to source host agent: http://10.20.0.11:8080/send]
    │  PC1 Host Agent opens NEW connection to http://10.20.0.12:8080/receive
    │  PC2 Host Agent logs to local buffer + ACKs
    │
    ▼
[Backend measures latency, updates Communication row, status=DELIVERED]
    │
    ▼
[WebSocket: {type:"communication_complete", project_id, full_record}]
    │
    ▼
[React subscribed to <uuid_A>]
    │  Animated edge between PC1 and PC2 lights up green for ~1.5s
    │  PC1 Message Window shows:  → "Hello PC2" sent ✓
    │  PC2 Message Window shows:  ← "Hello PC2" received ✓
    │  Communication Log appends new entry
```

### 11.4 Drag-and-Drop Persistence Flow (New!)

```
[User drags PC3 node to position (640, 200) on topology canvas]
    │
    ▼
[React Flow onNodeDragStop fires]
    │
    ▼
[PATCH /api/projects/<uuid>/nodes/pc3]
    │  body: {position_x: 640, position_y: 200}
    │
    ▼
[Project Service updates project_hosts row]
    │
    ▼
[User refreshes the page tomorrow]
    │
    ▼
[GET /api/projects/<uuid> returns PC3 with position (640, 200)]
[Topology canvas renders PC3 exactly where it was left]
```

---

## 12. Five Topology Templates — Visual Reference

### 12.1 Mesh (n = 5)

```
   pc1 ═══ pc2
   ║╲ ╲   ╱╱║
   ║  ╲ ╲ ╱  ║
   ║   ╲ ╳ ╱   ║
   ║    ╳   ╲   ║
   pc3 ═ pc4 ═ pc5

Edges:  n·(n−1)/2 = 10
```

### 12.2 Star (n = 6)

```
   pc2      pc3
     ╲      ╱
      ╲    ╱
       pc1
      ╱    ╲
     ╱      ╲
   pc5      pc4
              pc6

Edges: n−1 = 5
Hub: pc1
```

### 12.3 Ring (n = 6)

```
   pc1 ═ pc2
   ╱       ╲
 pc6       pc3
   ╲       ╱
   pc5 ═ pc4

Edges: n = 6
```

### 12.4 Bus / Linear (n = 5)

```
   pc1 ═ pc2 ═ pc3 ═ pc4 ═ pc5

Edges: n − 1 = 4
```

### 12.5 Tree (n = 7, binary)

```
              pc1
            ╱      ╲
         pc2        pc3
        ╱   ╲      ╱   ╲
      pc4  pc5   pc6  pc7

Edges: n − 1 = 6
```

---

## 13. Dashboard Modules

| Module | Professor Requirement | New Dynamic Behavior |
|--------|----------------------|----------------------|
| **LAN Builder** | (entry point) | User picks topology + count + subnet, creates project |
| **Projects Page** | (entry point) | Grid of project cards with start/stop/delete controls |
| **Topology View** | #2 Visualization | Per-project React Flow with drag-persist |
| **Host Monitor Cards** | #1 Monitor Hosts | Per-project host list with live CPU/RAM/Net |
| **Status LEDs** | #1 Monitor Hosts | Per-project, green/yellow/red on each node |
| **Trigger Panel** | #3 Simulate Communication | Per-project source/dest pickers |
| **Animated Edges** | #4 Real-time Flow | Per-project edge animations |
| **Message Windows** | #5 Display Messages | Per-project, per-host consoles |
| **Communication Log** | #3 + #5 | Per-project history |
| **Multi-Project Sidebar** | (new) | Switch active project; LAN Builder link |

---

## 14. UI Layout — User-Driven Workflow

```
┌────────────────────────────────────────────────────────────────────────┐
│  ContainerNet                              [Lab A ▼]  🟢 4/5 Hosts     │
├────────────┬───────────────────────────────────────────────────────────┤
│            │                                                           │
│ SIDEBAR    │   LAN BUILDER (default page after login)                  │
│            │                                                           │
│ • LAN Bldr │   ┌─────────────────────────────────────────────────┐    │
│ • Projects │   │  Name:    [Lab A                            ]   │    │
│ • Topology │   │  Topology: ┌──────┐ ┌──────┐ ┌──────┐           │    │
│ • Hosts    │   │            │ MESH │ │STAR  │ │RING  │  …        │    │
│ • Messages │   │            └──────┘ └──────┘ └──────┘           │    │
│ • Logs     │   │  Hosts:    [ 5 ]  (slider 3–32)                  │    │
│ • Alerts   │   │  Subnet:   [10.20.0.0/24        ]                │    │
│            │   │                                                  │    │
│            │   │   [  CREATE & START  ]                            │    │
│            │   └─────────────────────────────────────────────────┘    │
│            │                                                           │
│            │   PROJECTS GRID                                            │
│            │                                                           │
│            │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│            │   │ Lab A        │  │ Lab B        │  │ Lab C        │  │
│            │   │ Mesh · 5 h.  │  │ Star · 8 h.  │  │ Ring · 4 h.  │  │
│            │   │ 🟢 running   │  │ ⚫ stopped   │  │ 🟢 running   │  │
│            │   │ [Stop][Open] │  │ [Start][Open]│  │ [Open]       │  │
│            │   └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────┴───────────────────────────────────────────────────────────┘

After clicking "Open" on Lab A:

┌────────────────────────────────────────────────────────────────────────┐
│  Lab A (Mesh · 5 hosts · 10.20.0.0/24)            🟢 4/5 Hosts  [Lab A▼]│
├────────────┬───────────────────────────────────────────────────────────┤
│ SIDEBAR    │              NETWORK TOPOLOGY (React Flow, draggable)     │
│            │                                                           │
│ • Lab A    │     ┌──────┐        ───────►        ┌──────┐              │
│   Topology │     │ pc1  │    "Hello PC2"         │ pc2  │              │
│   Hosts    │     │ 🟢   │   ━━━━━━━━━━━         │ 🟢   │              │
│   Messages │     │.11   │   [animated packet]   │.12   │              │
│ • Logs     │     └──┬─┬─┘                       └─┬──┬─┘              │
│ • Alerts   │        │ ╲                          │  │                │
│            │        │  ╲─────────────────────┐   │  │                │
│            │        │                       │   │  │                │
│            │        ▼                       ▼   ▼  ▼                │
│            │     ┌──────┐                 ┌──────┐                   │
│            │     │ pc3  │                 │ pc4  │                   │
│            │     │ 🟢   │                 │ ⚫   │  (offline)         │
│            │     │.13   │                 │.14   │                    │
│            │     └──┬───┘                 └──────┘                    │
│            │        │                                                │
│            │        ▼                                                │
│            │     ┌──────┐                                            │
│            │     │ pc5  │                                            │
│            │     │ 🟢   │                                            │
│            │     │.15   │                                            │
│            │     └──────┘                                            │
│            │                                                           │
│            ├───────────────────────────────────────────────────────────┤
│            │                                                           │
│            │   TRIGGER PANEL          │   MESSAGE OUTPUT WINDOWS       │
│            │   ┌────────────────┐     │   ┌──── pc1 ────┬──── pc2 ──┐ │
│            │   │ From: [pc1  ▼] │     │   │ → Hello PC2 │ ← Hello   │ │
│            │   │ To:   [pc2  ▼] │     │   │ ✓ delivered │ ✓ 12ms    │ │
│            │   │ Proto:[HTTP ▼] │     │   │             │           │ │
│            │   │ Msg: Hello PC2 │     │   │ → status?   │ ← ok      │ │
│            │   │ [   SEND   ]   │     │   │ ✓           │ ✓ 6ms     │ │
│            │   └────────────────┘     │   └─────────────┴───────────┘ │
│            │                                                           │
└────────────┴───────────────────────────────────────────────────────────┘
```

---

## 15. Database Schema

### 15.1 `projects`
| Column        | Type          | Description                          |
|---------------|---------------|--------------------------------------|
| id            | UUID PK       | Project UUID                         |
| name          | VARCHAR       | User-given name                      |
| topology_type | VARCHAR(20)   | mesh / star / ring / bus / tree      |
| host_count    | INTEGER       | Number of hosts (3–32)               |
| subnet        | VARCHAR(20)   | e.g., `10.20.0.0/24`                 |
| gateway       | VARCHAR(20)   | Derived (e.g., `10.20.0.1`)          |
| status        | ENUM          | created / running / stopped / error  |
| network_name  | VARCHAR       | Docker bridge name (`proj_<uuid>_lan`)|
| created_at    | TIMESTAMP     |                                      |
| updated_at    | TIMESTAMP     |                                      |

### 15.2 `project_hosts`
| Column        | Type          | Description                          |
|---------------|---------------|--------------------------------------|
| id            | UUID PK       |                                      |
| project_id    | UUID FK       | → projects.id                        |
| host_id       | VARCHAR(20)   | "pc1", "pc2", ... unique per project |
| hostname      | VARCHAR(20)   | "PC1", "PC2", ...                    |
| container_id  | VARCHAR(100)  | Docker container ID (null until started) |
| ip_address    | VARCHAR(45)   | e.g., "10.20.0.11"                   |
| position_x    | FLOAT         | Saved drag-and-drop X                |
| position_y    | FLOAT         | Saved drag-and-drop Y                |
| status        | ENUM          | online / offline / unknown           |
| last_seen     | TIMESTAMP     |                                      |

Unique constraint: `(project_id, host_id)`

### 15.3 `project_edges`
| Column            | Type        | Description                    |
|-------------------|-------------|--------------------------------|
| id                | UUID PK     |                                |
| project_id        | UUID FK     | → projects.id                  |
| source_host_id    | VARCHAR(20) | "pc1"                          |
| dest_host_id      | VARCHAR(20) | "pc2"                          |

Unique constraint: `(project_id, source_host_id, dest_host_id)`

### 15.4 `communications`
| Column         | Type          | Description                  |
|----------------|---------------|------------------------------|
| id             | UUID PK       |                              |
| project_id     | UUID FK       | → projects.id  (NEW)         |
| source_host_id | VARCHAR(20)   |                              |
| dest_host_id   | VARCHAR(20)   |                              |
| protocol       | VARCHAR(20)   | HTTP / TCP / SQL / FILE      |
| payload        | TEXT          |                              |
| data_size      | INTEGER       |                              |
| latency_ms     | FLOAT         |                              |
| status         | ENUM          | pending / delivered / failed |
| timestamp      | TIMESTAMP     |                              |

### 15.5 `messages` (per-project, per-host event log)
| Column        | Type        | Description                       |
|---------------|-------------|-----------------------------------|
| id            | BIGSERIAL   |                                   |
| project_id    | UUID FK     | → projects.id                     |
| host_id       | VARCHAR(20) | The host that saw this message    |
| direction     | VARCHAR(4)  | `in` / `out`                      |
| peer_host_id  | VARCHAR(20) |                                   |
| payload       | TEXT        |                                   |
| timestamp     | TIMESTAMP   |                                   |

---

## 16. REST API Surface

### 16.1 Project Lifecycle
| Method | Endpoint                          | Description                          |
|--------|-----------------------------------|--------------------------------------|
| POST   | `/api/projects`                   | Create a project (form: name, topology, host_count, subnet) |
| GET    | `/api/projects`                   | List all projects                    |
| GET    | `/api/projects/{id}`              | Full project (nodes with positions, edges) |
| DELETE | `/api/projects/{id}`              | Stop + remove containers + remove network |
| POST   | `/api/projects/{id}/start`        | Spawn all host containers + create bridge |
| POST   | `/api/projects/{id}/stop`         | Stop all containers, keep project    |
| PATCH  | `/api/projects/{id}/nodes/{host_id}` | Update node position (x, y)       |

### 16.2 Project-Scoped Data
| Method | Endpoint                                                       | Description |
|--------|----------------------------------------------------------------|-------------|
| GET    | `/api/projects/{id}/hosts`                                     | List hosts in this project |
| POST   | `/api/health`                                                  | Host agent heartbeat (includes `project_id`) |
| POST   | `/api/projects/{id}/communications`                            | Trigger host-to-host comm |
| GET    | `/api/projects/{id}/communications`                            | Project comm history |
| GET    | `/api/projects/{id}/hosts/{host_id}/messages`                  | Per-host message history |
| POST   | `/api/projects/{id}/hosts/{host_id}/messages`                  | Host agent reports a message event |

### 16.3 Real-time
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS     | `/ws`    | Send `{type:"subscribe", project_id}` after connect to filter events for that project only |

---

## 17. WebSocket Events (per-project envelopes)

Every event envelope now includes `project_id` where applicable:

```json
{ "type": "host_status_change",
  "project_id": "<uuid>",
  "data": { "host_id": "pc1", "status": "online" },
  "ts": "..." }

{ "type": "communication_start",
  "project_id": "<uuid>",
  "data": { "id": "...", "source": "pc1", "destination": "pc2", ... } }

{ "type": "communication_complete",
  "project_id": "<uuid>",
  "data": { /* full Communication record */ } }

{ "type": "message",
  "project_id": "<uuid>",
  "data": { "host": "pc2", "direction": "in", "from": "pc1", "to": "pc2",
            "payload": "Hello PC2", "latency_ms": 12 } }
```

The frontend subscribes to a project on connect and only renders events whose `project_id` matches the active project.

---

## 18. Technology Stack

### Frontend
- **React 18 + TypeScript**
- **React Flow** — interactive topology graph with drag-and-drop
- **Tailwind CSS** — styling
- **Zustand** — state management (keyed by project_id)
- **Vite** — bundler
- **Axios** — API client
- **React Router v6** — `/builder`, `/projects`, `/projects/:id/*`
- **Dagre** — fallback auto-layout
- **lucide-react** — icons (including custom topology icons)

### Backend
- **Python 3.11**
- **FastAPI** — REST + WebSocket server
- **Docker SDK for Python (`docker` PyPI)** — container orchestration
- **SQLAlchemy 2.0** — async ORM
- **Pydantic v2** — validation
- **asyncpg** — async Postgres driver
- **httpx** — async HTTP client (to talk to host agents)
- **uvicorn** — ASGI server

### Infrastructure
- **Docker 24+** with **/var/run/docker.sock** mounted into the backend
- **Docker Compose v2** — for backend + db + frontend only

### Data Layer
- **PostgreSQL 15** — projects, hosts, edges, communications, messages

### Host Agent (unchanged)
- **Python 3.11** with `psutil`, `aiohttp`, `prometheus_client`

---

## 19. MVP Scope (10 Phases)

The 10 phases each deliver a complete, testable milestone:

| Phase | Output You Can See | Maps to Req # |
|-------|--------------------|---------------|
| **00** | This overview.md + new phases README written; static-vs-dynamic delta documented | — |
| **01** | Backend can create/stop/remove containers via Docker SDK; curl admin endpoints work | (foundation) |
| **02** | `POST /api/projects {topology, count, subnet}` creates a project with N nodes + edges, no containers yet | #2 |
| **03** | `POST /api/projects/{id}/start` spawns N real containers on a per-project bridge; heartbeats work | #6 |
| **04** | `/builder` UI form + `/projects/:id/topology` view with drag-and-drop persistence | #2 |
| **05** | Per-project host monitor; offline detection per project | #1 |
| **06** | Per-project trigger panel + communication log; cross-project isolation | #3 |
| **07** | WebSocket events scoped per project; animated edges per project | #4 |
| **08** | Per-project, per-host message windows; Node-RED-style debug panes | #5 |
| **09** | Projects home grid; multi-project dashboard; cleanup on restart; docs finalized | — |

After Phase 09, **all six professor requirements are satisfied** — and they hold for any user-defined topology, any host count, and any number of coexisting projects.

---

## 20. Demo Scenarios

1. **"Build a mesh lab in 30 seconds"** — User opens `/builder`, picks mesh + 8 hosts + `10.40.0.0/24`, hits Create. Backend creates the project, spawns 8 containers on a fresh bridge, dashboard loads with the topology. User drags hosts around — positions save instantly.
2. **"Run two labs side-by-side"** — User creates Project A (ring, 4 hosts) and Project B (star, 6 hosts). Both run simultaneously on different bridges. UI shows both in the projects grid. Triggering a message in A never affects B.
3. **"Detect a failure"** — User kills one host in Project A via `docker stop`. Within 20s, that node's LED turns red in A's topology only. B is unaffected.
4. **"Stop a project, restart later"** — User clicks Stop on Project A. All 5 containers stop. Project row remains with status=`stopped`. Tomorrow, user clicks Start — exactly the same containers come back on the same bridge.
5. **"Add a new topology later"** — Developer adds `generate_torus(n)` to `topology_generator.py`. Adds the new option to the LAN Builder dropdown. No DB schema changes. Done.

---

## 21. Non-Functional Requirements

- **Latency** — WebSocket events to dashboard < 500 ms.
- **Scalability** — Support 3–32 hosts per project, 5+ coexisting projects on a single VM with 16 GB RAM.
- **Resilience** — A failed host doesn't crash the dashboard; offline state reflected. Orphaned containers cleaned on backend startup.
- **Reproducibility** — `docker compose up -d --build` brings up the platform; the rest is user-driven.
- **Extensibility** — Adding a new topology = one new function in `topology_generator.py`. Adding a new host agent capability = one new file in `host-agent/`.
- **Resource safety** — Soft cap of 32 hosts per project; backend validates and surfaces a friendly error.

---

## 22. Security Considerations

### Docker socket access

The backend needs to talk to the Docker daemon to spawn and tear down project containers. Mounting `/var/run/docker.sock` directly into the backend is **equivalent to giving that container root on the host** — any vulnerability in the backend becomes a host compromise.

For production deployments, use a **Docker socket proxy** (e.g., [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy)) that exposes a filtered HTTP API and **whitelists only the endpoints** the backend actually needs (containers, networks, images — but NOT exec, attach, volumes, or privileged mode). The backend then points at `DOCKER_HOST=tcp://docker-proxy:2375` and never touches the socket directly.

### Spawned host containers

Every project host container is launched with defense-in-depth hardening:

- `cap_drop=["ALL"]` + `cap_add=["NET_BIND_SERVICE"]` only if required
- `security_opt=["no-new-privileges:true"]`
- `user="1000:1000"` (non-root)
- `mem_limit="256m"`, `cpu_quota=50000` (resource caps)
- `read_only` root filesystem with `tmpfs` for `/tmp`
- Image allow-list — only `containernet-host-base:latest` can be spawned; any other image name is rejected

### Admin endpoints

Development-time admin endpoints (`/api/admin/*`) are gated behind an `ADMIN_TOKEN` environment variable. Requests must include the correct `X-Admin-Token` header. In production, `ADMIN_TOKEN` is left unset, and the dependency refuses every admin request with `403 Forbidden`. The admin surface is removed entirely after Phase 09.

### Network isolation

Subnet validation prevents users from claiming subnets that conflict with the host's networking (`172.17.0.0/16`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`, etc.). Project networks are isolated by default — cross-project traffic requires explicit opt-in.

### Audit log

Every container start, stop, and remove writes a structured log line with: project ID, container ID, user (when auth is added), and timestamp. These logs feed into the platform's central observability stack.

---

## 23. Final Project Definition

> **ContainerNet is a self-service web platform that lets users design and launch their own container-based virtual LANs. A user picks a topology (mesh, star, ring, bus, tree), a host count, and a subnet from a browser form; the backend spins up that exact LAN as real Docker containers on a per-project bridge network. The user can then monitor every host (CPU, RAM, network, status), visualize and drag-arrange the interactive topology, trigger communications between any two hosts, watch animated packets flow in real time across the chosen topology, and read Node-RED-style per-host message windows — all scoped to their project. Multiple projects can coexist on isolated bridges. The platform is the foundation for a future Virtual Cyber Range.**

### Academic Domains Covered
- **Computer Networks** — LAN emulation, TCP/IP, latency, topologies (mesh, star, ring, bus, tree)
- **Container Virtualization** — Docker, per-project bridge networks, container lifecycle
- **Distributed Systems** — multi-host communication, project isolation, container orchestration
- **DevOps & Observability** — Prometheus metrics, structured logging, container health
- **Real-Time Systems** — WebSockets, per-project event channels
- **Data Visualization** — React Flow topology with persistence, Dagre auto-layout
- **Full-Stack Web Development** — React + FastAPI + PostgreSQL + Docker SDK

---

## 24. Quick Pitch (for Viva / README)

> "ContainerNet is a **self-service virtual LAN platform**. Open the dashboard, pick a topology and how many hosts you want, hit Create — and the backend builds that exact LAN as real Docker containers on its own private bridge network. You can monitor every host, drag hosts around on the topology (positions persist), trigger messages between any two hosts, watch animated packets flow in real time over the topology edges, and read per-host message consoles — exactly the Node-RED debug experience. Multiple projects can run side-by-side in complete isolation. The platform is inspired by Kathara and Containerlab for the network layer and Node-RED for the visualization paradigm, and serves as the foundation for our future Virtual Cyber Range."

---

## 25. References (from Project Guide)

- [Kathara Framework](https://github.com/KatharaFramework/Kathara)
- [Containerlab](https://github.com/srl-labs/containerlab)
- [OpenCyberRange](https://opencyberrange.com/)
- [PeerJ CS-1574 — Cyber Range Design](https://peerj.com/articles/cs-1574/)
- [awesome-vulnerable](https://github.com/kaiiyer/awesome-vulnerable)
- [Node-RED](https://nodered.org/)
- [ContainerFlow](https://github.com/RGJorge/ContainerFlow)
- [Atlas Dashboard](https://github.com/karam-ajaj/atlas)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
- [React Flow](https://reactflow.dev/)
