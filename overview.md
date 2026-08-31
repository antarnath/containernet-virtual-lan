# ContainerNet — Project Overview

> **A Container-based Virtual LAN with Real-Time Host Monitoring, Network Topology Visualization, and Node-RED Style Communication Flow Simulation**

---

## 1. Project Title

**ContainerNet: A Web-Based Virtual Cyber Range Platform for Monitoring, Visualizing, and Simulating Host-to-Host Communication in a Container-Based LAN**

---

## 2. Project Vision (As Directed by Project Guide)

> *"We need to monitor hosts, visualize network topology, simulate host-to-host communication, show real-time data flow, and display messages between hosts — where every host is a single container. This is the foundation for our future target: a **Virtual Cyber Lab**."* 

This document describes the foundation phase of ContainerNet. The platform is being designed in a way that it can be **extended into a full Virtual Cyber Range** in later phases (inspired by Kathara, Containerlab, OpenCyberRange, and the PeerJ CS-1574 paper).

### 2.1 Six Core Requirements (from Project Guide)

The system MUST deliver all six of the following:

| # | Requirement | Implementation |
|---|-------------|----------------|
| 1 | **Monitor Hosts** | Each host container exposes health, status, CPU, RAM, network, uptime |
| 2 | **Visualize Network Topology** | Interactive graph (React Flow) showing all hosts and their connections |
| 3 | **Simulate Host-to-Host Communication** | Node-RED style trigger → execute → output flow |
| 4 | **Show Real-time Data Flow** | Animated packets traveling along topology edges (WebSocket-driven) |
| 5 | **Display Messages Between Hosts** | Dedicated **Output Window** per host showing received/sent messages (like Node-RED debug pane) |
| 6 | **Container-based Virtual LAN** | Each host = 1 Docker container on a shared bridge network (Kathara/Containerlab style) |

---

## 3. Inspiration & References

The architecture draws inspiration from existing container-networking and observability tools studied during the project research phase:

| Reference | What we Learn |
|-----------|---------------|
| **[Kathara Framework](https://github.com/KatharaFramework/Kathara)** | Lightweight container-based network emulation — each "router/host" is a container on a shared bridge |
| **[Containerlab](https://github.com/srl-labs/containerlab)** | Declarative topology definitions for containerized network labs |
| **[OpenCyberRange](https://opencyberrange.com/)** | Cyber range architecture — multi-host virtual lab with web control plane |
| **[PeerJ CS-1574](https://peerj.com/articles/cs-1574/)** | Academic foundation for cyber range design and learning |
| **[Node-RED](https://nodered.org/)** | Visual flow programming — drag nodes, wire them, see live output in debug panel |
| **[awesome-vulnerable](https://github.com/kaiiyer/awesome-vulnerable)** | Reference for deploying vulnerable training apps inside the virtual LAN |
| **ContainerFlow & Atlas** | Reference dashboards for visualizing host/container topology |

Our approach: **borrow Kathara's container-per-host philosophy**, **Containerlab's declarative topology**, and **Node-RED's flow-output paradigm**, then add a **real-time web dashboard** on top.

---

## 4. Problem Statement

Traditional network monitoring tools (Grafana, Prometheus, Portainer, Zabbix) provide **resource-level metrics** and **container management**, but they **do not visualize real-time communication between hosts** in a LAN.

Existing container-lab tools (Kathara, Containerlab) are excellent for **emulating networks** but lack a **rich, web-based real-time visualization layer** that shows:

- Which host is talking to which host
- What payload is being transmitted
- The latency and status of each communication
- A Node-RED style **debug/output window** showing live messages per host

ContainerNet bridges this gap: **a virtual LAN built from Docker containers, with a Node-RED inspired web dashboard for live monitoring, topology visualization, and communication flow simulation.**

---

## 5. Goals & Objectives

### 5.1 Primary Goals (Phase 1 — Foundation)

1. **Container-based Virtual LAN** — Each host (PC1, PC2, PC3, PC4) is a Docker container connected via a bridge network.
2. **Host Monitoring** — Real-time status, CPU, RAM, network, heartbeat per host.
3. **Network Topology Visualization** — Interactive dashboard showing all hosts and their links.
4. **Host-to-Host Communication Simulation** — Trigger messages between any two hosts using TCP/HTTP.
5. **Real-time Data Flow** — Animated packet visualization on topology edges (live).
6. **Message Display Windows** — Per-host output panel showing incoming/outgoing messages (Node-RED style).

### 5.2 Future Goals (Phase 2+ — Virtual Cyber Lab)

Building on this foundation, ContainerNet will evolve into a **Virtual Cyber Range**:

- Deploy vulnerable services (DVWA, Metasploitable-like apps) inside hosts.
- Simulate attacks/defenses between hosts.
- Capture and visualize attack flows on the same dashboard.
- Multi-user lab sessions with isolated topologies.

---

## 6. Core Concept

### 6.1 Every Host is a Container

Following the **Kathara / Containerlab model**, every "PC" in our virtual LAN is a single Docker container:

```
PC1  ──►  container: pc1    (IP: 10.10.0.11)
PC2  ──►  container: pc2    (IP: 10.10.0.12)
PC3  ──►  container: pc3    (IP: 10.10.0.13)
PC4  ──►  container: pc4    (IP: 10.10.0.14)
```

All containers are attached to a **single Docker bridge network** `containernet_lan` (subnet `10.10.0.0/24`) — this *is* the virtual LAN.

### 6.2 Host Agent (Runs Inside Each Container)

Every host container runs a lightweight **Python Host Agent** that exposes four capabilities:

```
Host Agent
├── 1. Health Monitor      → Heartbeat to backend every 5s
├── 2. Metrics Exporter    → CPU/RAM/Net on /metrics (Prometheus format)
├── 3. Message Receiver    → TCP/HTTP server to receive messages
└── 4. Message Sender      → Outbound client to send to peers
```

### 6.3 Communication Paradigm (Node-RED Inspired)

Inspired by **Node-RED**, the dashboard exposes a **flow-based interface**:

- **Trigger** — User picks a source host (PC1) and a destination host (PC2).
- **Action** — User defines a payload ("Hello PC2") and protocol (TCP/HTTP).
- **Execute** — Backend orchestrates the communication between hosts.
- **Output** — Live message appears in:
  - PC1's output window (sent)
  - PC2's output window (received)
  - The animated topology edge (data in transit)
  - The global communication log

---

## 7. High-Level Architecture

```
                            ┌──────────────────────────────┐
                            │             USER             │
                            └──────────────┬───────────────┘
                                           │ Browser
                                           ▼
                ┌────────────────────────────────────────────────────┐
                │           REACT DASHBOARD (Web UI)                 │
                │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
                │ │  Topology    │ │  Host        │ │  Message     │ │
                │ │  View        │ │  Monitor     │ │  Output      │ │
                │ │  (ReactFlow) │ │  (Live Stats)│ │  Windows     │ │
                │ └──────────────┘ └──────────────┘ └──────────────┘ │
                │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
                │ │  Trigger     │ │  Comm Log    │ │  Animated    │ │
                │ │  Panel       │ │  (History)   │ │  Data Flow   │ │
                │ └──────────────┘ └──────────────┘ └──────────────┘ │
                └────────────────────────┬───────────────────────────┘
                                         │ REST API + WebSocket
                                         ▼
                ┌────────────────────────────────────────────────────┐
                │            FASTAPI BACKEND (Control Plane)         │
                │ ┌────────────────┐ ┌─────────────────────────────┐ │
                │ │ Topology Engine│ │ Communication Orchestrator │ │
                │ └────────────────┘ └─────────────────────────────┘ │
                │ ┌────────────────┐ ┌─────────────────────────────┐ │
                │ │ Metrics Service│ │ WebSocket Broadcaster       │ │
                │ └────────────────┘ └─────────────────────────────┘ │
                └────┬──────────────────┬──────────────────┬─────────┘
                     │                  │                  │
                     ▼                  ▼                  ▼
              ┌───────────┐       ┌───────────┐       ┌───────────┐
              │PostgreSQL │       │   Redis   │       │ Prometheus│
              │(Logs/Hsts)│       │ (Pub/Sub) │       │ (Metrics) │
              └───────────┘       └───────────┘       └─────┬─────┘
                                                             │
                                       ┌─────────────────────┼─────────────────────┐
                                       ▼                     ▼                     ▼
                                 ┌───────────┐         ┌───────────┐         ┌───────────┐
                                 │ cAdvisor  │         │Node Exprtr│         │ Host Agent│
                                 │(Container │         │(Host HW)  │         │ (per host)│
                                 │  metrics) │         │           │         │           │
                                 └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
                                       │                     │                     │
                                       └──────────┬──────────┴──────────┬──────────┘
                                                  ▼                     ▼
                                    ┌──────────────────────────────────────────────┐
                                    │       DOCKER VIRTUAL LAN (Bridge)            │
                                    │       containernet_lan (10.10.0.0/24)        │
                                    │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
                                    │  │  PC1   │ │  PC2   │ │  PC3   │ │  PC4   │ │
                                    │  │.11     │ │.12     │ │.13     │ │.14     │ │
                                    │  │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │ │
                                    │  └────────┘ └────────┘ └────────┘ └────────┘ │
                                    └──────────────────────────────────────────────┘
```

---

## 8. Project Structure (Monorepo)

```
ContainerNet/
├── README.md
├── overview.md                      # ← This file
├── docker-compose.yml               # Full stack orchestration
│
├── infra/                           # Network & host container definitions
│   ├── network.yml                  # Virtual LAN (bridge) definition
│   ├── hosts/
│   │   ├── pc1.Dockerfile
│   │   ├── pc2.Dockerfile
│   │   ├── pc3.Dockerfile
│   │   └── pc4.Dockerfile
│   └── prometheus/
│       └── prometheus.yml
│
├── host-agent/                      # Python agent running INSIDE every host container
│   ├── agent.py                     # Main entrypoint
│   ├── health_monitor.py            # Heartbeat to backend
│   ├── metrics_exporter.py          # /metrics on :9100
│   ├── message_server.py            # TCP/HTTP receiver
│   ├── message_client.py            # Outbound sender
│   ├── config.py                    # Reads HOST_ID, BACKEND_URL from env
│   └── requirements.txt
│
├── backend/                         # FastAPI control plane
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── database.py
│   │   ├── api/
│   │   │   ├── hosts.py             # CRUD for hosts
│   │   │   ├── communications.py    # Trigger + log communications
│   │   │   ├── topology.py          # Build graph for frontend
│   │   │   ├── metrics.py           # Query Prometheus
│   │   │   └── health.py            # Heartbeat ingest
│   │   ├── engines/
│   │   │   ├── topology_engine.py
│   │   │   ├── communication_orchestrator.py  # ← Node-RED style flow engine
│   │   │   └── alert_engine.py
│   │   ├── models/
│   │   │   ├── host.py
│   │   │   ├── communication.py
│   │   │   ├── heartbeat.py
│   │   │   └── alert.py
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── prometheus_client.py
│   │   │   ├── docker_client.py     # Talk to Docker daemon
│   │   │   └── websocket_manager.py
│   │   └── ws/
│   │       └── events.py
│   ├── migrations/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                        # React dashboard
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Topbar.tsx
│   │   │   ├── topology/
│   │   │   │   ├── TopologyView.tsx       # React Flow
│   │   │   │   ├── HostNode.tsx           # Custom node: name + status LED
│   │   │   │   └── AnimatedEdge.tsx       # Animated packet on edge
│   │   │   ├── host-monitor/
│   │   │   │   ├── HostCard.tsx
│   │   │   │   └── HostStats.tsx          # CPU/RAM/Net
│   │   │   ├── message-window/            # ← NODE-RED style output
│   │   │   │   ├── MessageWindow.tsx      # Per-host console
│   │   │   │   └── MessageBubble.tsx
│   │   │   ├── trigger/                   # ← Node-RED style input
│   │   │   │   ├── TriggerPanel.tsx       # Pick src/dst/payload
│   │   │   │   └── ProtocolSelector.tsx
│   │   │   ├── comm-log/
│   │   │   │   ├── CommunicationLog.tsx
│   │   │   │   └── CommunicationDetails.tsx
│   │   │   └── dashboard/
│   │   │       ├── StatCard.tsx
│   │   │       └── NetworkOverview.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx              # Home with stats
│   │   │   ├── TopologyPage.tsx           # Main topology view
│   │   │   ├── HostsPage.tsx              # Host monitoring
│   │   │   ├── CommunicationsPage.tsx     # Communication log
│   │   │   └── MessageWindowsPage.tsx     # All host output windows
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useHosts.ts
│   │   │   └── useMessages.ts
│   │   ├── store/                         # Zustand
│   │   ├── types/
│   │   └── api/
│   │       └── client.ts
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   └── package.json
│
├── docs/
│   ├── architecture.md
│   ├── communication-protocol.md
│   ├── references.md                # Links from professor
│   └── screenshots/
│
└── scripts/
    ├── seed_hosts.py
    └── demo_traffic.py              # Generate sample traffic for demos
```

---

## 9. Virtual LAN Design

Following the **Kathara/Containerlab** pattern — each host is an isolated container, all on one bridge network:

```
Docker Network: containernet_lan
Subnet:          10.10.0.0/24
Gateway:         10.10.0.1

┌─────────────────────────────────────────────────────────────┐
│  Host    Container ID    IP            Host Agent Port       │
├─────────────────────────────────────────────────────────────┤
│  PC1     pc1             10.10.0.11    :9100 (metrics)      │
│                                       :8080 (messages)      │
│  PC2     pc2             10.10.0.12    :9100 / :8080        │
│  PC3     pc3             10.10.0.13    :9100 / :8080        │
│  PC4     pc4             10.10.0.14    :9100 / :8080        │
└─────────────────────────────────────────────────────────────┘
```

Hosts can ping, curl, or open raw TCP sockets to each other through this bridge — exactly as if they were physical machines on a switch.

---

## 10. Data Flow

### 10.1 Host Monitoring Flow

```
[PC1 Container]
    │  Host Agent runs psutil.cpu_percent(), etc.
    │  Exposes /metrics on :9100 (Prometheus format)
    ▼
[Prometheus]
    │  Scrapes every 15s
    │  Stores time-series
    ▼
[FastAPI Metrics Service]
    │  PromQL queries on demand
    ▼
[React Dashboard]
    │  /hosts page → live CPU, RAM, Net cards
    ▼
[User sees PC1 stats updating in real time]
```

### 10.2 Host Heartbeat Flow

```
[PC1 Host Agent]
    │  Every 5s: POST /api/health {host_id: "pc1", ts: ...}
    ▼
[FastAPI]
    │  Updates hosts.last_seen
    │  Sets status = online if < 15s ago, else offline
    ▼
[WebSocket broadcast]
    │  { event: "host_status", host: "PC1", status: "online" }
    ▼
[Dashboard]
    │  Topology node PC1 turns green 🟢
```

### 10.3 Host-to-Host Communication Flow (Node-RED Style)

```
[User on Dashboard]
    │  Opens Trigger Panel
    │  Selects: Source = PC1, Destination = PC2, Protocol = TCP, Payload = "Hello PC2"
    │  Clicks "Send"
    ▼
[React → FastAPI: POST /api/communications]
    │
    ▼
[FastAPI Communication Orchestrator]
    │  Resolves PC1 → 10.10.0.11:8080
    │  Resolves PC2 → 10.10.0.12:8080
    │  Generates communication_id
    │  Emits WebSocket: { event: "comm_start", id, src:PC1, dst:PC2 }
    ▼
[PC1 Host Agent receives "send" command]
    │  Opens TCP socket to 10.10.0.12:8080
    │  Sends JSON: { from: "pc1", to: "pc2", payload: "Hello PC2" }
    ▼
[PC2 Host Agent receives message]
    │  Logs to local buffer
    │  POSTs back to FastAPI: { event: "message_received", id, status: "ok" }
    ▼
[FastAPI]
    │  Calculates latency
    │  Persists communication record
    │  Broadcasts WebSocket: { event: "comm_complete",
    │                            id, src:PC1, dst:PC2,
    │                            payload: "Hello PC2",
    │                            latency_ms: 12, status: "delivered" }
    ▼
[Dashboard]
    ├── PC1 Message Window shows: → "Hello PC2" sent ✓
    ├── PC2 Message Window shows: ← "Hello PC2" received ✓
    ├── Animated edge lights up: PC1 ════════► PC2  (packet slides)
    ├── Communication Log appends new entry
    └── Latency badge shows: 12 ms
```

### 10.4 Alert Flow

```
[Prometheus / custom threshold]
    │  Host offline > 15s OR CPU > 90%
    ▼
[FastAPI Alert Engine]
    │  Creates alert record
    │  WebSocket: { event: "alert", host: "PC2", severity: "high" }
    ▼
[Dashboard]
    └── Alert toast + alert panel entry
```

---

## 11. Dashboard Modules — Mapped to the Six Core Requirements

| Module | Requirement Satisfied | Description |
|--------|----------------------|-------------|
| **Topology View** | #2 Network Topology Visualization | Interactive React Flow graph with all hosts as nodes |
| **Host Monitor Cards** | #1 Monitor Hosts | Per-host live CPU/RAM/Net/Uptime |
| **Status LEDs on Nodes** | #1 Monitor Hosts | Green/yellow/red on each topology node |
| **Trigger Panel** | #3 Simulate Communication | Pick src/dst/protocol/payload, click Send |
| **Animated Edges** | #4 Real-time Data Flow | Packets travel along edges when comm happens |
| **Message Windows** | #5 Display Messages | Per-host output console (Node-RED debug pane style) |
| **Communication Log** | #3 + #5 | History of all messages with metadata |
| **Container List** | #6 Container-based Virtual LAN | Shows Docker container for each host |
| **Live Stats Sidebar** | #1 + #4 | Network-wide counters (active comms, msgs/sec) |

---

## 12. UI Layout — Node-RED Inspired

```
┌────────────────────────────────────────────────────────────────────────┐
│  ContainerNet                                          🟢 4/4 Hosts   │
├────────────┬───────────────────────────────────────────────────────────┤
│            │                                                           │
│ SIDEBAR    │              NETWORK TOPOLOGY (React Flow)                │
│            │                                                           │
│ • Home     │     ┌──────┐        ───────►        ┌──────┐              │
│ • Topology │     │ PC1  │    "Hello PC2"         │ PC2  │              │
│ • Hosts    │     │ 🟢   │   ━━━━━━━━━━━         │ 🟢   │              │
│ • Messages │     │.11   │   [animated packet]   │.12   │              │
│ • Logs     │     └──┬───┘                       └──┬───┘              │
│ • Alerts   │        │                              │                  │
│            │        │         ┌──────┐             │                  │
│            │        └────────►│ PC3  │◄────────────┘                  │
│            │                  │ 🟢   │                                │
│            │                  │.13   │                                │
│            │                  └──┬───┘                                │
│            │                     │                                    │
│            │                     ▼                                    │
│            │                  ┌──────┐                                │
│            │                  │ PC4  │                                │
│            │                  │ ⚫   │  (offline)                     │
│            │                  └──────┘                                │
│            │                                                           │
│            ├───────────────────────────────────────────────────────────┤
│            │                                                           │
│            │   TRIGGER PANEL          │   MESSAGE OUTPUT WINDOWS       │
│            │   ┌────────────────┐     │   ┌──── PC1 ────┬──── PC2 ──┐ │
│            │   │ From: [PC1  ▼] │     │   │ → Hello PC2 │ ← Hello   │ │
│            │   │ To:   [PC2  ▼] │     │   │ ✓ delivered │ ✓ 12ms    │ │
│            │   │ Proto:[TCP  ▼] │     │   │             │           │ │
│            │   │ Msg: Hello PC2 │     │   │ → status?   │ ← ok      │ │
│            │   │ [   SEND   ]   │     │   │ ✓           │ ✓ 6ms     │ │
│            │   └────────────────┘     │   └─────────────┴───────────┘ │
│            │                                                           │
└────────────┴───────────────────────────────────────────────────────────┘
```

---

## 13. Communication Workflow (Step-by-Step)

| Step | Actor | Action |
|------|-------|--------|
| 1 | User | Opens dashboard, sees live topology |
| 2 | User | Opens **Trigger Panel** (Node-RED style) |
| 3 | User | Selects **source** host (PC1) |
| 4 | User | Selects **destination** host (PC2) |
| 5 | User | Chooses **protocol** (TCP / HTTP / SQL / FILE) |
| 6 | User | Types **payload** (`Hello PC2`) |
| 7 | User | Clicks **Send** |
| 8 | Backend | Generates communication ID, resolves IPs |
| 9 | Backend | Emits `comm_start` event → dashboard animates edge |
| 10 | Backend | Tells PC1's Host Agent to send the message |
| 11 | PC1 Agent | Opens TCP socket to PC2:8080, transmits payload |
| 12 | PC2 Agent | Receives message, logs locally, ACKs back |
| 13 | Backend | Records latency, persists to DB |
| 14 | Backend | Emits `comm_complete` event with full metadata |
| 15 | Dashboard | Appends to **Communication Log** |
| 16 | Dashboard | Updates **PC1 Message Window** (`→ sent`) |
| 17 | Dashboard | Updates **PC2 Message Window** (`← received`) |
| 18 | Dashboard | Edge animation completes; latency badge appears |

---

## 14. Database Schema

### 14.1 `hosts`
| Column        | Type          | Description                  |
|---------------|---------------|------------------------------|
| id            | UUID PK       | Internal ID                  |
| hostname      | VARCHAR       | "PC1", "PC2", …              |
| container_id  | VARCHAR       | Docker container ID          |
| ip_address    | INET          | e.g., "10.10.0.11"           |
| mac_address   | VARCHAR       | Optional                     |
| status        | ENUM          | online / offline / unknown   |
| last_seen     | TIMESTAMP     | Last heartbeat               |
| agent_port    | INTEGER       | 8080                         |
| metrics_port  | INTEGER       | 9100                         |
| created_at    | TIMESTAMP     |                              |

### 14.2 `communications`
| Column         | Type          | Description                  |
|----------------|---------------|------------------------------|
| id             | UUID PK       | Communication ID             |
| source_host_id | FK → hosts    | Sender                       |
| dest_host_id   | FK → hosts    | Receiver                     |
| protocol       | VARCHAR       | TCP / HTTP / SQL / FILE      |
| payload        | TEXT          | Message body                 |
| data_size      | INTEGER       | Bytes                        |
| latency_ms     | FLOAT         | RTT                          |
| status         | ENUM          | delivered / failed / pending |
| timestamp      | TIMESTAMP     | When sent                    |

### 14.3 `heartbeats`
| Column   | Type      | Description       |
|----------|-----------|-------------------|
| id       | BIGSERIAL |                   |
| host_id  | FK        |                   |
| ts       | TIMESTAMP | Heartbeat time    |

### 14.4 `alerts`
| Column    | Type       | Description           |
|-----------|------------|-----------------------|
| id        | UUID PK    |                       |
| host_id   | FK         |                       |
| severity  | ENUM       | low / medium / high   |
| message   | TEXT       | Human-readable        |
| resolved  | BOOLEAN    |                       |
| timestamp | TIMESTAMP  |                       |

---

## 15. REST API Surface

| Method | Endpoint                          | Description                    |
|--------|-----------------------------------|--------------------------------|
| GET    | `/api/hosts`                      | List all hosts                 |
| GET    | `/api/hosts/{id}`                 | Get host details               |
| POST   | `/api/health`                     | Host agent heartbeat           |
| POST   | `/api/communications`             | **Trigger host-to-host comm**  |
| GET    | `/api/communications`             | List communications (paged)   |
| GET    | `/api/communications/{id}`        | Communication details          |
| GET    | `/api/topology`                   | Hosts + edges for graph        |
| GET    | `/api/metrics/{host_id}`          | Live metrics for a host        |
| GET    | `/api/metrics/aggregate`          | Network-wide metrics           |
| GET    | `/api/alerts`                     | Active alerts                  |
| GET    | `/api/messages/{host_id}`         | Message buffer for a host      |
| WS     | `/ws`                             | Real-time events               |

---

## 16. WebSocket Events

**Host lifecycle**
```json
{ "event": "host_online",  "host": "PC1" }
{ "event": "host_offline", "host": "PC3" }
{ "event": "host_status",  "host": "PC1", "status": "online" }
```

**Communication lifecycle**
```json
{ "event": "comm_start",    "id": "uuid", "source": "PC1", "destination": "PC2" }

{
  "event": "comm_complete",
  "id": "uuid",
  "source": "PC1",
  "destination": "PC2",
  "protocol": "TCP",
  "payload": "Hello PC2",
  "data_size": 11,
  "latency_ms": 12,
  "status": "delivered",
  "timestamp": "2026-08-28T19:30:21Z"
}
```

**Message Window updates**
```json
{
  "event": "message",
  "host": "PC2",
  "direction": "in",         // "in" | "out"
  "from": "PC1",
  "to": "PC2",
  "payload": "Hello PC2",
  "latency_ms": 12,
  "ts": "2026-08-28T19:30:21Z"
}
```

**Alerts**
```json
{ "event": "alert", "host": "PC2", "severity": "high", "message": "CPU > 90%" }
```

---

## 17. Technology Stack

### Frontend
- **React 18 + TypeScript**
- **React Flow** — interactive topology graph with custom nodes/edges
- **Tailwind CSS** — styling
- **Recharts** — metrics charts
- **Zustand** — state management
- **Vite** — bundler
- **Axios / React Query** — API client
- **lucide-react** — icons

### Backend
- **Python 3.11**
- **FastAPI** — REST + WebSocket server
- **SQLAlchemy 2.0** — ORM
- **Alembic** — migrations
- **Pydantic v2** — validation
- **asyncpg** — async Postgres driver
- **redis-py** — pub/sub
- **httpx** — async HTTP client (to talk to host agents)

### Infrastructure
- **Docker 24+**
- **Docker Compose v2** — orchestration
- **Docker Bridge Network** — virtual LAN

### Monitoring Stack
- **Prometheus** — metrics collection
- **cAdvisor** — container metrics
- **Node Exporter** — host metrics

### Data Layer
- **PostgreSQL 15** — persistent storage
- **Redis 7** — pub/sub, cache

### Host Agent
- **Python 3.11** with `psutil`, `aiohttp`, `prometheus_client`, `fastapi`

---

## 18. MVP Scope (Phase 1 — Build First)

Deliver a working demo that satisfies all six core requirements:

✅ Docker LAN with **3 hosts** (PC1, PC2, PC3) on `containernet_lan` (10.10.0.0/24)
✅ Host Agent running inside each host container (Python)
✅ FastAPI backend with:
  - Host registry
  - Communication orchestrator (TCP)
  - WebSocket broadcaster
  - Topology endpoint
✅ React dashboard with:
  - Topology view (React Flow) → **Req #2**
  - Host status LEDs + metrics → **Req #1**
  - Trigger panel (src/dst/protocol/payload) → **Req #3**
  - Animated edges during communication → **Req #4**
  - Per-host message output windows → **Req #5**
  - Container list view → **Req #6**
✅ Communication log + latency display
✅ One demo flow: PC1 → "Hello PC2" → PC2, with full animation

---

## 19. Development Phases

| Phase | Focus | Maps To |
|-------|-------|---------|
| **Phase 1** | Foundation: Docker LAN + Host Agent + basic dashboard | All 6 core requirements (MVP) |
| **Phase 2** | Multi-protocol: HTTP, SQL, FILE communications | Extends #3 |
| **Phase 3** | Rich monitoring: Prometheus + cAdvisor + Recharts | Enhances #1 |
| **Phase 4** | Alerts & history | Enhances #1, #5 |
| **Phase 5** | **Virtual Cyber Lab**: deploy vulnerable apps, attack visualization | Future target |
| **Phase 6** | Multi-user lab sessions, lab topologies as YAML | Future target |

---

## 20. Demo Scenarios

1. **"Show me the LAN"** — User opens dashboard, sees 3–4 host nodes connected by edges, all green.
2. **"PC1 says hello to PC2"** — User clicks PC1 → PC2, types "Hello PC2", presses Send. Edge animates; PC2's output window shows the received message.
3. **"Detect a failure"** — Kill PC3 container manually. Within 15s, PC3 node turns red; alert toast appears.
4. **"Trigger an HTTP request"** — User picks protocol=HTTP, payload=GET /status. PC1 sends an HTTP request to PC2, response is shown in both output windows.
5. **"Replicate the lab"** — User edits `topology.yml` to add PC5, restarts stack; new host appears in the dashboard.

---

## 21. Non-Functional Requirements

- **Latency:** WebSocket events to dashboard < 500 ms.
- **Scalability:** Support 10–20 hosts in Phase 1; architecture supports 100+.
- **Resilience:** A failed host must not crash the dashboard; offline state reflected.
- **Reproducibility:** `docker compose up` brings up the entire stack.
- **Extensibility:** Adding a new host = one container + one agent config; no code changes.

---

## 22. Final Project Definition

> **ContainerNet is a web-based platform that creates a container-based virtual LAN — where each host is a Docker container on a bridge (Kathara/Containerlab style) — and provides a Node-RED inspired web dashboard for monitoring hosts, visualizing network topology, simulating host-to-host communication, showing real-time animated data flow, and displaying messages between hosts in dedicated output windows. This is the foundation for a future Virtual Cyber Range.**

### Academic Domains Covered
- **Computer Networks** — LAN emulation, TCP/IP, latency
- **Container Virtualization** — Docker, bridge networks (Kathara/Containerlab)
- **Distributed Systems** — multi-host communication
- **DevOps & Observability** — Prometheus, cAdvisor, Node Exporter
- **Real-Time Systems** — WebSockets, live updates
- **Data Visualization** — React Flow topology, Recharts metrics
- **Full-Stack Web Development** — React + FastAPI + PostgreSQL

---

## 23. Quick Pitch (for Viva / README)

> "ContainerNet is a **web-based virtual LAN platform** built from Docker containers. Each 'PC' is a container on a shared bridge network. From a single dashboard, you can **monitor every host**, **see the live network topology**, **trigger communications** between any two hosts (just like Node-RED), **watch animated data packets** flow in real time, and **view messages in per-host output windows** — exactly the way Node-RED displays debug output. The platform is inspired by Kathara and Containerlab for the network layer and Node-RED for the visualization paradigm, and serves as the foundation for our future **Virtual Cyber Lab**."

---

## 24. References (from Project Guide)

- [Kathara Framework](https://github.com/KatharaFramework/Kathara)
- [Containerlab](https://github.com/srl-labs/containerlab)
- [OpenCyberRange](https://opencyberrange.com/)
- [PeerJ CS-1574 — Cyber Range Design](https://peerj.com/articles/cs-1574/)
- [awesome-vulnerable](https://github.com/kaiiyer/awesome-vulnerable)
- [Node-RED](https://nodered.org/)
- [ContainerFlow](https://github.com/RGJorge/ContainerFlow)
- [Atlas Dashboard](https://github.com/karam-ajaj/atlas)