# ContainerNet — Full System Architecture

> **A complete visual walkthrough of how the platform works, from the user
> dragging a router onto a blank canvas to a packet crossing a real Docker
> bridge between two containers the user wired together.**

This document is the single source of truth for the **target** architecture
of ContainerNet. It shows the system as the user experiences it and as the
code is structured. Some pieces are already built; others are the roadmap
laid out in `phases/milestone-3/` and the upcoming `phases/milestone-4/`.

## 0. The one rule this design does not break

**There are no templates. There is no preset topology. There is no
"home", "office", or "two-office" starter. The canvas is always blank.
The user is the network engineer.**

ContainerNet is a Docker-based Cisco Packet Tracer. Packet Tracer does not
ask "would you like the 3-router office template?" — it opens a blank canvas
and gives the user a toolbox. We do the same. Every node the user sees,
they placed. Every wire, they drew. Every IP, they typed. The system's
only job is to faithfully materialize whatever they drew into real Docker
containers and bridges, and to faithfully tear it down when they stop.

The 5-node-kind taxonomy (host, switch, router, attacker, server) and the
per-link bridge model exist because **networks are made of those things**,
not because we are prescribing a shape. The user can draw 1 host or 50.
The backend does not assume.

---

## 1. The user's mental model (the top of the system)

Everything in ContainerNet revolves around **5 primitives** — the same
primitives a network engineer uses in Cisco Packet Tracer.

| # | Primitive | What it is | Example |
|---|-----------|------------|---------|
| 1 | **Project** | The whole network the user is building | "Lab A" (any shape the user draws) |
| 2 | **Node** | A device on the canvas (router, switch, host, attacker, server) | Router-1, Host-3, Attacker-1 |
| 3 | **Interface** | A port on a node. Has an IP and a subnet mask. | Router-1 `eth0` = 10.30.10.1/24 |
| 4 | **Link** | A wire between two interfaces. Both ends share a subnet. | Router-1.eth0 ↔ Switch-1.port1 on 10.30.10.0/24 |
| 5 | **Capture** | A passive sniffer on a link. The user views its output as the "wire view". | The capture on the 10.30.10.0/24 link |

The user **builds** a network by placing nodes, configuring their interfaces,
and drawing links between interfaces. The **system** turns that into real
Docker containers, bridges, and capture points.

---

## 2. The user experience end-to-end

### 2.1 The dashboard at a glance

```
┌────────────────────────────────────────────────────────────────────┐
│  ContainerNet        [New]  [Open]  [Docs]  [About]                │
├────────────────────────────────────────────────────────────────────┤
│  Toolbar:  [🖥️ Host] [🔀 Switch] [📡 Router] [🖧 Server]          │
│            [💣 Attacker] [─ Wire]                                  │
│            [▶ Start]  [⏹ Stop]  [💾 Save]  [🗑 Delete]            │
├────────────────────────────────────────────────────────────────────┤
│ Sidebar:        │                                                  │
│ • Topology      │              Canvas (React Flow)                │
│ • Wires         │                                                  │
│ • Routers       │       (drag, drop, draw wires)                   │
│ • Hosts         │                                                  │
│ • Attacks       │                                                  │
└─────────────────┴──────────────────────────────────────────────────┘
```

### 2.2 A real user session — the user is the engineer

The user opens ContainerNet and the canvas is **blank**. There is no
"start here" template, no sample topology, no suggested shape. The only
things on screen are a left-side toolbox with five draggable node kinds
(host, switch, router, server, attacker), a wire tool, and an empty
canvas. The user decides what to build.

For this walkthrough, the user has decided to build a network with
**3 routers, 3 switches, 10 hosts, and 1 attacker** — the kind of topology
a networking class would set as a lab exercise. They could just as easily
build 1 host, or 50 routers in a mesh, or 2 hosts connected by a single
wire. The system does not care.

#### Step A — drop devices

The user clicks `Router` in the toolbox, then clicks the canvas. A router
icon appears. They repeat — clicking each toolbox item, then clicking
the canvas where they want it — until they've placed 3 routers, 3
switches, 10 hosts, and 1 attacker wherever they like. The canvas now
shows roughly:

```
Canvas (positions are whatever the user chose):

   [Router-1]              [Router-2]              [Router-3]

   [Switch-1]               [Switch-2]               [Switch-3]

   H1 H2 H3 H4 Attk        H5 H6                   H7 H8 H9 H10
```

The system has assigned each node a UUID and a default name
(`Router-1`, `Host-1`, etc.). The user can rename anything by clicking
the label.

#### Step B — configure interfaces

The user double-clicks Router-1. A side panel opens:

```
┌──────────────────────────────────────┐
│ Router-1                             │
│ Kind: Router                         │
├──────────────────────────────────────┤
│ Interfaces                           │
│   eth0   10.30.10.1   /24  [×]       │
│   eth1   10.30.99.1   /30  [×]       │
│   [+ Add interface]                  │
├──────────────────────────────────────┤
│ Static Routes                        │
│   10.30.20.0/24 via 10.30.99.2  [×]  │
│   10.30.30.0/24 via 10.30.99.2  [×]  │
│   [+ Add route]                      │
├──────────────────────────────────────┤
│ [Save]                               │
└──────────────────────────────────────┘
```

The user types the IPs they want. The user repeats for Router-2 and
Router-3, typing whatever addresses fit the design they have in mind.
There is no preset. The user might use `10.0.0.0/16` everywhere, or
three unrelated private ranges, or class A — anything valid.

For each host, the user sets one interface's IP (e.g. Host-1 `eth0` =
`10.30.10.11/24`). The system **automatically suggests a default route**
= the IP of whichever router is on the same wire, but the user can
override it.

#### Step C — draw wires

The user clicks the `Wire` tool, then clicks Router-1's `eth0`, then
clicks Switch-1's first port. A line is drawn. The system suggests a
subnet based on the two endpoint IPs and the user accepts or edits.

The user keeps going: each switch has as many ports as they wired up,
each going to one host on the same subnet. Then they wire the three
routers to each other using their `eth1` interfaces on small `/30`
subnets. After all wires are drawn, the topology is whatever the user
built. In this example it happens to be:

```
   [Router-1]──────10.30.99.0/30──────[Router-2]
       │                                   │
       │ 10.30.98.0/30                     │ 10.30.97.0/30
       │                                   │
   [Router-3]                              (no further wire here)

   [Router-1].eth0 ── 10.30.10.0/24 ── [Switch-1]
       [Switch-1].port1 ── Host-1.eth0
       [Switch-1].port2 ── Host-2.eth0
       [Switch-1].port3 ── Host-3.eth0
       [Switch-1].port4 ── Host-4.eth0
       [Switch-1].port5 ── Attacker-1.eth0

   [Router-2].eth0 ── 10.30.20.0/24 ── [Switch-2]
       [Switch-2].port1 ── Host-5.eth0
       [Switch-2].port2 ── Host-6.eth0

   [Router-3].eth0 ── 10.30.30.0/24 ── [Switch-3]
       [Switch-3].port1 ── Host-7.eth0
       [Switch-3].port2 ── Host-8.eth0
       [Switch-3].port3 ── Host-9.eth0
       [Switch-3].port4 ── Host-10.eth0
```

But the user could have drawn anything. A triangle of routers with no
switches, a single host with no router, ten routers in a ring, a host
directly wired to a router with no switch in between — all equally valid.
The shape lives in the user's head and on the canvas, not in the code.

#### Step D — save and start

The user clicks **Save** (writes the topology to the database) and then
**Start** (asks the backend to build it). The backend validates the
topology — no duplicate IPs, every wired interface configured, every
link has both ends on a compatible subnet — and then spawns one Docker
container per node and one bridge per link. There is no "office" or
"subnet" concept in the schema; a "subnet" is whatever set of nodes
share a bridge.

If the validation finds a problem (e.g. two interfaces on the same wire
with mismatched subnets), the offending wire is highlighted in red and
the Start button stays disabled until the user fixes it. The user is
the engineer; the system refuses to start a broken network.

#### Step E — use it

The canvas now shows every node with a green "running" indicator. The
user can:

- **Click Host-1** → see `ifconfig` (live), CPU, memory, a "ping" button.
  They type the IP of a host on a different router's subnet and click
  ping. It works, because the packet crosses whatever path the user's
  routing tables define.

- **Click Router-1** → see `ip route` (live, refreshed every 2s). The
  contents are exactly the static routes the user typed in Step B:
  ```
  10.30.10.0/24 dev eth0 proto kernel scope link src 10.30.10.1
  10.30.20.0/24 via 10.30.99.2 dev eth1
  10.30.30.0/24 via 10.30.99.2 dev eth1
  10.30.99.0/30 dev eth1 proto kernel scope link src 10.30.99.1
  ```
  and `ip neigh` (live):
  ```
  10.30.10.11 dev eth0 lladdr 02:42:0a:1e:0a:0b REACHABLE
  10.30.10.12 dev eth0 lladdr 02:42:0a:1e:0a:0c REACHABLE
  ...
  ```

- **Click any wire** → open the **wire view** for that wire. It's a
  live packet capture on the Docker bridge that backs that wire. The
  user sees the ARPs, the ICMPs, every frame as it goes by.

- **Click the wire between two routers** → another wire view. The user
  sees the same ICMP echo packets passing through the router, with TTL
  decremented from 64 to 63.

#### Step F — add an attacker

The user right-clicks the attacker node they placed and picks an attack
mode. They choose **"ARP spoof Router-1"**. The attack starts. The
wire view on Router-1's LAN segment shows gratuitous ARP packets
flying by: "10.30.10.1 is at <attacker-mac>".

A few seconds later, the user opens **Router-1's `ip neigh` panel** and
sees something alarming: the entry for Host-1 now shows the attacker's
MAC, not Host-1's real MAC. The router's ARP cache has been
**poisoned**.

The user then watches the wire view: the next packet Host-1 sends goes
to the attacker's MAC. The attacker is now **silently in the middle of
every conversation** between Host-1 and the rest of the network.

---

## 3. The high-level system architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       BROWSER                                       │
│   React + TypeScript + Vite + React Flow + Zustand                 │
│                                                                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│   │ Canvas   │  │ Wire     │  │ Router   │  │ Hosts    │            │
│   │ Editor   │  │ View     │  │ Panel    │  │ List     │            │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │
│        │              │              │              │                  │
│        │   HTTP REST + WebSocket + SSE per project                  │
└────────┼──────────────┼──────────────┼──────────────┼─────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  FASTAPI BACKEND                                     │
│                                                                       │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │                    API Layer (routers)                    │     │
│   │  /projects /nodes /interfaces /links /packets /routers   │     │
│   └──────────────────────────────────────────────────────────┘     │
│                              │                                       │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │                   Service Layer                            │     │
│   │  project_service   — validate & orchestrate topology      │     │
│   │  node_service      — CRUD on nodes, interfaces            │     │
│   │  link_service      — CRUD on links, IP uniqueness         │     │
│   │  container_service — spawn/stop/remove Docker              │     │
│   │  bridge_service    — one Docker bridge per link           │     │
│   │  packet_service    — read capture NDJSON, serve SSE        │     │
│   │  router_proxy      — proxy /route /arp to router agent     │     │
│   │  comm_service      — trigger host-to-host messages         │     │
│   │  message_service   — per-host message log                  │     │
│   └──────────────────────────────────────────────────────────┘     │
│                              │                                       │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │                    Data Layer                              │     │
│   │  Project, ProjectNode, ProjectInterface, ProjectLink,     │     │
│   │  Communication, Message  (SQLAlchemy 2.0 async + asyncpg)  │     │
│   └──────────────────────────────────────────────────────────┘     │
│                              │                                       │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │                  Infra Clients                             │     │
│   │  docker-py   — talks to /var/run/docker.sock               │     │
│   │  httpx       — async HTTP to containers                    │     │
│   └──────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ Docker SDK + HTTP
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DOCKER DAEMON (host)                            │
│                                                                       │
│   For the example project the user built in §2.2 (3 routers,        │
│   3 switches, 10 hosts, 1 attacker, 8 wires):                       │
│                                                                       │
│   ┌─ Bridges (one per wire the user drew) ─────────────────────┐  │
│   │  proj_<id>_link0  10.30.10.0/24  (Router-1 ↔ Switch-1)      │  │
│   │  proj_<id>_link1  10.30.20.0/24  (Router-2 ↔ Switch-2)      │  │
│   │  proj_<id>_link2  10.30.30.0/24  (Router-3 ↔ Switch-3)      │  │
│   │  proj_<id>_link3  10.30.99.0/30  (Router-1 ↔ Router-2)      │  │
│   │  proj_<id>_link4  10.30.98.0/30  (Router-1 ↔ Router-3)      │  │
│   │  ... etc. (one per wire the user drew)                       │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Routers (one per router node the user placed) ───────────┐  │
│   │  proj_<id>_router-1   image: containernet-router-base       │  │
│   │    - attached to link0, link3, link4 (via eth0/eth1/eth2)    │  │
│   │    - ip_forward=1, static routes installed                   │  │
│   │    - tiny HTTP agent on :9090 (ip route, ip neigh, ip link)  │  │
│   │  proj_<id>_router-2   same image, different config            │  │
│   │  proj_<id>_router-3   same image, different config            │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Switches (one per switch node the user placed) ────────────┐  │
│   │  proj_<id>_switch-1   image: containernet-switch-base       │  │
│   │    - attached to link0 (multi-port: one veth per host)       │  │
│   │    - tiny HTTP agent on :9091 (MAC table, port list)        │  │
│   │  ...                                                          │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Hosts (one per host node the user placed) ─────────────────┐  │
│   │  proj_<id>_host-1  image: containernet-host-base             │  │
│   │    - attached to link0 (via eth0)                             │  │
│   │    - default route: whatever the user configured              │  │
│   │    - agent on :8080 (HTTP send/receive), :9100 (metrics)     │  │
│   │  ...                                                          │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Attacker (one per attacker node the user placed) ─────────┐  │
│   │  proj_<id>_attacker-1  image: containernet-host-base        │  │
│   │    - same as a host, but AGENT_ROLE=attacker                 │  │
│   │    - attack_engine.py runs the chosen scenario               │  │
│   │    - e.g. ARP spoof: "I am 10.30.10.1" every 1s             │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Capture containers (one per link) ──────────────────────────┐  │
│   │  proj_abc_capture-link0  image: containernet-capture-base    │  │
│   │    - tcpdump on the bridge interface                         │  │
│   │    - NDJSON output via host-bind-mounted file                │  │
│   │  ... (one per link)                                          │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌─ Backend's control-plane bridge ─────────────────────────────┐  │
│   │  containernet_containernet_lan  (10.10.0.0/24)              │  │
│   │    - backend container is here                               │  │
│   │    - every spawned node is also here                         │  │
│   │    - so the backend can reach every container's HTTP agent   │  │
│   └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. What happens when the user clicks Start

This is the single most important flow in the system. It is the
moment the user's mental model becomes a real network.

```
USER clicks [▶ Start]
       │
       ▼
BROWSER:  POST /api/projects/{id}/start
       │
       ▼
BACKEND:  project_service.start_project(project_id)
       │
       │
       ├──► 1. VALIDATE THE TOPOLOGY
       │      - Every node has at least one interface
       │      - Every interface has an IP + mask (except switches' ports)
       │      - Every link has both ends on a compatible subnet
       │      - No duplicate IPs across the whole project
       │      - Routers' static routes point to reachable next-hops
       │      - If validation fails → return 400 with a clear error
       │
       ├──► 2. FOR EACH LINK, CREATE A DOCKER BRIDGE
       │      bridge_service.create_bridge(link)
       │        → docker network create proj_abc_linkN --driver bridge
       │            --ipam-config subnet=<link.subnet>,gateway=<...>
       │        → returns the bridge name
       │      Repeat for every link. The number of bridges equals
       │      the number of wires the user drew.
       │
       ├──► 3. FOR EACH NODE, SPAWN A CONTAINER
       │      container_service.spawn_node(node, interfaces, links)
       │        → Pick the right image based on node.kind:
       │          • router    → containernet-router-base
       │          • switch    → containernet-switch-base
       │          • host      → containernet-host-base
       │          • server    → containernet-host-base + a flag
       │          • attacker  → containernet-host-base + AGENT_ROLE=attacker
       │
       │        → docker run the image, no network attached yet
       │
       │        → For each interface on this node:
       │            find the link it participates in
       │            docker network connect <bridge> <container>
       │              --ip <interface.ip_address>
       │
       │        → Inside the container, configure each interface:
       │            ip addr add <ip>/<mask> dev <iface>
       │            ip link set <iface> up
       │
       │        → For HOSTS:
       │            ip route add default via <gateway_ip>
       │          (the gateway is the OTHER end of the link, if it's a router)
       │
       │        → For ROUTERS:
       │            sysctl -w net.ipv4.ip_forward=1
       │            For each static route:
       │              ip route add <dest> via <next_hop> dev <iface>
       │
       │        → Store the container_id on the ProjectNode row
       │
       ├──► 4. FOR EACH LINK, SPAWN A CAPTURE CONTAINER
       │      container_service.spawn_capture(link)
       │        → docker run containernet-capture-base
       │            --network=host --pid=host
       │            --cap-add=NET_RAW --cap-add=NET_ADMIN
       │            --env PROJECT_BRIDGE_NAME=<link.bridge_name>
       │            --volume /var/lib/containernet/captures:/captures
       │        → The container runs:
       │            tcpdump -i <bridge> -U -l -tttt -nn -w -
       │              | python3 capture_shim.py > /captures/<id>.ndjson
       │        → The backend can later `docker exec cat` this file
       │
       ├──► 5. UPDATE DATABASE
       │      For each ProjectNode: set container_id, status=running
       │      Set Project.status = running
       │      Commit
       │
       └──► 6. RETURN THE UPDATED PROJECT
              GET /api/projects/{id} now shows everything in "running"
```

**Total time**: about 2-5 seconds for the example project, depending on
how many containers need to be created.

---

## 5. What happens when the user clicks a wire to see packets

The **wire view** is the live packet capture for one specific link. It is
the most important teaching surface in the system.

```
USER clicks on the wire between Router-1 and Switch-1
       │
       ▼
BROWSER:  GET /api/projects/{id}/links/{link_id}/packets/stream
       │
       ▼
BACKEND:  packet_service.stream_packets(link_id)
       │
       ├──► Find the capture container for this link
       │      container_service.get_link_capture(link_id)
       │        → look up the link's bridge_name
       │        → find the container with PROJECT_LINK=<link_id>
       │
       ├──► Open an SSE (Server-Sent Events) stream
       │      StreamingResponse(media_type="text/event-stream")
       │
       └──► In a background thread, poll the capture container
              every 100ms:
                 docker exec <capture_id> cat /captures/<id>.ndjson
              Parse any new NDJSON lines (events with id > last_seen_id)
              Push them into the SSE queue
              Browser receives them as:
                 data: {"id": 42, "ts": "...", "l2": {...}, ...}\n\n
```

The browser renders them with the existing packet log UI. The user sees:

- **Conversation view**: packets grouped into TCP conversations
- **Raw packet log**: every packet in order, with L2/L3/L4/L7 details
- **Filters**: by source/dest IP, by protocol, by size

This is **Wireshark's view** of one specific wire in the user's network.

---

## 6. What happens when the user opens a router's panel

The router panel shows what the **router itself** knows — its routing
table, its ARP table, its interface status, and live CPU/memory.

```
USER clicks Router-1
       │
       ▼
BROWSER:  GET /api/projects/{id}/routers/{router_node_id}/state
       │
       ▼
BACKEND:  router_proxy.get_state(router_node_id)
       │
       ├──► Find the router's container_id from the database
       │
       ├──► Find the router's IP on the backend bridge
       │      (so the backend can reach its HTTP agent)
       │      docker inspect <container>
       │        → Networks[containernet_containernet_lan].IPAddress
       │
       ├──► Make 4 parallel HTTP requests to the router's agent:
       │      GET http://<router_ip>:9090/route
       │      GET http://<router_ip>:9090/arp
       │      GET http://<router_ip>:9090/interfaces
       │      GET http://<router_ip>:9090/stats
       │
       └──► Return all 4 responses as one JSON object
              {
                "route":     { "lines": ["...", "..."] },
                "arp":       { "lines": ["...", "..."] },
                "interfaces":{ "lines": ["...", "..."] },
                "stats":     { "cpu_percent": 1.2, "memory_percent": 8.4 }
              }
```

The browser polls this endpoint every 2 seconds and re-renders the panel.
The user sees a **live view of the router's internal state** — exactly what
they'd see if they typed `show ip route` and `show ip arp` on a real Cisco
router.

### 6.1 Anomaly detection

The router panel also runs **anomaly detection** in the browser. It
compares the current `ip neigh` snapshot to the previous one, and if any
MAC address has changed for a given IP, it raises a banner:

```
┌──────────────────────────────────────────────────┐
│ ⚠ ARP CACHE ANOMALY                             │
│                                                  │
│ 10.30.10.1 was at 02:42:0a:1e:0a:01              │
│ 10.30.10.1 is now at 02:42:0a:1e:0a:99  ← MISMATCH│
│                                                  │
│ Possible ARP spoofing. Check who's on this link. │
└──────────────────────────────────────────────────┘
```

This is the **first line of defense** the user has against an attacker.
It is also the most striking demo in the system: a one-line ARP packet
from the attacker changes the router's view of the network.

---

## 7. What happens when the user triggers a communication

This is the **same as today** — the user picks source + dest + payload,
clicks Send, and the backend orchestrates a real HTTP message between
the two hosts. The difference is that the message now **crosses a real
network** (potentially through routers) and the wire views show its
journey.

```
USER: source=Host-1, dest=Host-5, payload="hello"
       │
       ▼
BROWSER:  POST /api/projects/{id}/communications
       │
       ▼
BACKEND:  comm_service.trigger_communication(project_id, body)
       │
       ├──► 1. Validate both hosts belong to the project and are running
       │
       ├──► 2. Insert a Communication row (status=pending)
       │
       ├──► 3. Publish "communication_start" WebSocket event
       │      (frontend subscribers see "in flight" indicator on the edge)
       │
       ├──► 4. Resolve source host's IP on the backend bridge
       │      (so the backend can reach its :8080 HTTP agent)
       │
       ├──► 5. POST http://<host1>:8080/send
       │      body: {
       │        "comm_id": "...",
       │        "target_host_id": "host-5",
       │        "target_ip": "10.30.20.11",   ← Host-5's project IP
       │        "payload": "hello"
       │      }
       │
       ├──► 6. Host-1's agent receives /send
       │      → opens a NEW connection to http://10.30.20.11:8080/receive
       │      → the connection goes:
       │           Host-1 → Switch-1 → Router-1 → Router-2 → Switch-2 → Host-5
       │      → 9 packets minimum (TCP handshake + request + response + close)
       │
       ├──► 7. Backend measures round-trip time
       │      → updates Communication row (status=delivered, latency_ms=...)
       │
       ├──► 8. Publish "communication_complete" WebSocket event
       │      (frontend sees the edge light up green for ~1.5s)
       │
       └──► 9. Both /send and /receive fire message events
              → message table gets 2 rows (1 out from Host-1, 1 in from Host-5)
              → WebSocket "message" events fan out to subscribers
              → per-host message consoles update in real time
```

**The wire view is the magic here.** While the communication is in flight,
the user can switch to ANY of the wire views (one per wire they drew) and
see the packets as they cross that specific link:

- **Wire on link0 (10.30.10.0/24 LAN)**: SYN from Host-1, SYN-ACK to Host-1
- **Wire on link3 (Router-1 ↔ Router-2)**: SYN forwarded, SYN-ACK forwarded
  (with TTL decremented by 1)
- **Wire on link1 (10.30.20.0/24 LAN)**: SYN arriving at Host-5, SYN-ACK
  leaving Host-5

Three captures of the same packet, each one a hop closer to its
destination. This is **Wireshark-on-every-hop** and it's the most
pedagogically valuable feature in the system.

---

## 8. The data model in detail

5 tables for the user's topology, plus 2 tables for the messaging system.

```
┌─ projects ──────────────────────────────────────────────────────┐
│  id            UUID PRIMARY KEY                                 │
│  name          TEXT                                             │
│  status        ENUM (draft / running / stopped / error)          │
│  created_at    TIMESTAMPTZ                                      │
│  updated_at    TIMESTAMPTZ                                      │
└─────────────────────────────────────────────────────────────────┘
        │
        │ 1:N
        ▼
┌─ project_nodes ────────────────────────────────────────────────┐
│  id            UUID PRIMARY KEY                                 │
│  project_id    UUID → projects.id  ON DELETE CASCADE            │
│  node_id       TEXT  (unique within project: "router-1")        │
│  kind          ENUM (router / switch / host / attacker / server)│
│  hostname      TEXT                                             │
│  position_x    FLOAT                                            │
│  position_y    FLOAT                                            │
│  container_id  TEXT  (set after Start)                          │
│  status        ENUM (draft / running / stopped / error)          │
└─────────────────────────────────────────────────────────────────┘
        │
        │ 1:N
        ▼
┌─ project_interfaces ───────────────────────────────────────────┐
│  id            UUID PRIMARY KEY                                 │
│  node_id       UUID → project_nodes.id                          │
│  name          TEXT  ("eth0", "port1", "GigabitEthernet0/0")    │
│  ip_address    TEXT  NULL  (NULL = unconfigured)                │
│  subnet_mask   TEXT  ("/24", "/30")                             │
│  mac_address   TEXT  (set at Start)                             │
│  is_up         BOOLEAN (default true)                           │
└─────────────────────────────────────────────────────────────────┘
        ▲                ▲
        │                │
        │                │ a_interface_id / b_interface_id
        │                │
┌─ project_links ────────────────────────────────────────────────┐
│  id             UUID PRIMARY KEY                                │
│  project_id     UUID → projects.id                              │
│  a_interface_id UUID → project_interfaces.id                    │
│  b_interface_id UUID → project_interfaces.id                    │
│  subnet         TEXT  ("10.30.10.0/24")  — derived from IPs     │
│  bridge_name    TEXT  (set at Start: "proj_abc_link0")          │
└─────────────────────────────────────────────────────────────────┘
        │
        │ 1:1
        ▼
┌─ project_captures ──────────────────────────────────────────────┐
│  id             UUID PRIMARY KEY                                │
│  link_id        UUID → project_links.id                         │
│  container_id   TEXT  (the capture container)                   │
│  file_path      TEXT  (host path to the NDJSON output)          │
└─────────────────────────────────────────────────────────────────┘

┌─ communications (unchanged from today) ────────────────────────┐
│  id, project_id, source_host_id, dest_host_id, protocol,        │
│  payload, data_size, latency_ms, status, timestamp              │
└─────────────────────────────────────────────────────────────────┘

┌─ messages (unchanged from today) ───────────────────────────────┐
│  id, project_id, host_id, direction, peer_host_id,              │
│  comm_id, payload, protocol, timestamp                          │
└─────────────────────────────────────────────────────────────────┘
```

### The 5 primitives mapped to the 5 tables

| Primitive   | Table                  | Notes                                            |
|-------------|------------------------|--------------------------------------------------|
| Project     | `projects`             | The container                                    |
| Node        | `project_nodes`        | One row per device on the canvas                 |
| Interface   | `project_interfaces`   | One or more per node                             |
| Link        | `project_links`        | One per wire the user drew                       |
| Capture     | `project_captures`     | One per link, derived at Start                   |

The capture is **derived** because the user never configures it directly —
the system creates one per link at Start time. It could be computed on
the fly from the link's bridge_name, but having a row makes the
container_id easy to find.

---

## 9. The container images

Three base images do the heavy lifting. The host image and the attacker
image are the **same** image; the difference is the `AGENT_ROLE` env var.

```
┌─ containernet-host-base ─────────────────────────────────────────┐
│  Base: Alpine 3.19                                              │
│  Includes: python3, aiohttp, prometheus-client, psutil, curl,  │
│            iproute2, busybox-extras, tcpdump                     │
│  Agent:                                                         │
│    agent.py              main entrypoint                        │
│    health_monitor.py     POSTs /api/health every 5s             │
│    message_service.py    /send /receive /messages on :8080      │
│    message_reporter.py   POSTs per-message events to backend    │
│    metrics_exporter.py   /healthz /metrics on :9100              │
│    attack_engine.py      runs when AGENT_ROLE=attacker          │
│  Env: PROJECT_ID, HOST_ID, HOST_IP, GATEWAY_IP, BACKEND_URL    │
└─────────────────────────────────────────────────────────────────┘

┌─ containernet-router-base ───────────────────────────────────────┐
│  Base: containernet-host-base                                   │
│  Adds: nothing — just configures ip_forward and routes         │
│  Agent:                                                         │
│    router_agent.py       HTTP server on :9090                   │
│                            /route, /arp, /interfaces, /stats   │
│  Env: PROJECT_ID, NODE_ID, plus one PORT_<N>_IP per interface  │
│  Privileges: NET_ADMIN (to set ip_forward, ip route)            │
└─────────────────────────────────────────────────────────────────┘

┌─ containernet-switch-base ───────────────────────────────────────┐
│  Base: Alpine 3.19                                              │
│  Includes: a small Python service that exposes:                 │
│    /mac-table     current MAC → port mapping                    │
│    /ports         list of ports + status (up/down)              │
│  Agent:                                                         │
│    switch_agent.py                                              │
│  Note: in v1, the switch is rendered as a node but is           │
│        functionally identical to a transparent bridge.          │
│        It exists for visualization and pedagogical reasons.     │
└─────────────────────────────────────────────────────────────────┘

┌─ containernet-capture-base ──────────────────────────────────────┐
│  Base: Alpine 3.19                                              │
│  Includes: tcpdump, python3, iproute2-minimal, bash             │
│  Shim:                                                          │
│    capture_shim.py      reads binary pcap, writes NDJSON        │
│  Run:                                                           │
│    tcpdump -i <bridge> -U -l -tttt -nn -vvv -w -                │
│      | python3 capture_shim.py > $CAPTURE_FILE                  │
│  Privileges: NET_RAW + NET_ADMIN, network_mode=host, pid=host   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. The project layout

```
ContainerNet/
├── backend/                            # FastAPI backend
│   ├── app/
│   │   ├── main.py                     # FastAPI app + lifespan
│   │   ├── core/                       # config, db, docker client
│   │   ├── api/                        # HTTP routes (one file per resource)
│   │   ├── ws/                         # WebSocket event manager
│   │   ├── schemas/                    # Pydantic models
│   │   ├── models/                     # SQLAlchemy ORM
│   │   └── services/                   # Domain logic
│   │       ├── project_service.py      # start/stop/delete orchestration
│   │       ├── node_service.py         # CRUD on nodes + interfaces
│   │       ├── link_service.py         # CRUD on links + validation
│   │       ├── container_service.py    # Docker SDK wrapper
│   │       ├── bridge_service.py       # one Docker bridge per link
│   │       ├── packet_service.py       # capture NDJSON → SSE
│   │       ├── router_proxy.py         # proxy to router's HTTP agent
│   │       ├── comm_service.py         # trigger host-to-host messages
│   │       ├── message_service.py      # per-host message log
│   │       └── orphan_service.py       # cleanup at startup
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                           # React + Vite + React Flow
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                     # routes
│   │   ├── api/                        # Axios wrappers
│   │   ├── components/
│   │   │   ├── canvas/                 # React Flow editor
│   │   │   │   ├── Canvas.tsx          # the main editor
│   │   │   │   ├── DeviceNode.tsx      # router/switch/host node UI
│   │   │   │   ├── WireEdge.tsx        # the wire between two ports
│   │   │   │   └── DevicePanel.tsx     # side panel for editing
│   │   │   ├── wire-view/              # per-link packet capture
│   │   │   │   ├── WireView.tsx
│   │   │   │   ├── ConversationView.tsx
│   │   │   │   └── RawPacketView.tsx
│   │   │   ├── router-panel/           # router's ip route / ip neigh
│   │   │   │   ├── RouterPanel.tsx
│   │   │   │   ├── RouteTable.tsx
│   │   │   │   ├── ArpTable.tsx
│   │   │   │   └── AnomalyBanner.tsx
│   │   │   ├── hosts/                  # per-host views
│   │   │   ├── trigger/                # send a communication
│   │   │   └── attacks/                # M3 attacker scenarios
│   │   ├── hooks/                      # useWebSocket, usePacketStream, etc.
│   │   ├── pages/                      # one file per route
│   │   ├── store/                      # Zustand stores
│   │   ├── types/                      # TypeScript types
│   │   └── utils/                      # tcpClassifier, etc.
│   ├── Dockerfile                      # builds static bundle
│   └── nginx.conf                      # /api proxy to backend
│
├── host-agent/                         # runs inside every host/attacker container
│   ├── agent.py                        # main entrypoint
│   ├── config.py                       # env-driven config
│   ├── health_monitor.py
│   ├── message_service.py
│   ├── message_reporter.py
│   ├── metrics_exporter.py
│   ├── attack_engine.py                # M3 attacker scenarios
│   └── capture_shim.py                 # also used in capture containers
│
├── router-agent/                       # runs inside every router container
│   └── router_agent.py                 # HTTP server: /route, /arp, /interfaces
│
├── switch-agent/                       # runs inside every switch container
│   └── switch_agent.py                 # HTTP server: /mac-table, /ports
│
├── infra/hosts/                        # Dockerfiles
│   ├── host-base.Dockerfile
│   ├── router-base.Dockerfile
│   ├── switch-base.Dockerfile
│   └── capture-base.Dockerfile
│
├── phases/                             # design docs (one folder per milestone)
│   ├── milestone-1/                    # ✅ phases 00-09
│   ├── milestone-2/                    # ✅ M2-00 through M2-07 (capture pipeline)
│   └── milestone-3/                    # 📋 attacker scenarios + router
│
├── scripts/
│   ├── smoke_test.sh                   # end-to-end test
│   └── tests/
│
├── docker-compose.yml
├── README.md
├── overview.md                         # original product overview
├── architecture.md                     # ← THIS FILE
└── .env.example
```

---

## 11. The user's view of one project

After the user has built and started a project, the dashboard
shows them 5 main views, all keyed by project.

### 11.1 Topology / Canvas view (`/projects/:id/canvas`)

The main editor and the live visualization. After Start, the canvas
shows every node with its container status and every wire as a colored
line. The user can:

- Drag nodes to rearrange
- Click a node to open its side panel
- Right-click a wire to open the wire view
- Right-click a node to access quick actions (ping, view metrics, etc.)

### 11.2 Wire view (`/projects/:id/links/:link_id/log`)

The per-link packet capture. Two tabs:

- **Conversation view**: packets grouped into TCP conversations
- **Raw packet log**: every packet in order, with full L2/L3/L4/L7 detail

In the example project, the user can switch between wire views (one
per wire they drew). The same ICMP packet appears in multiple views as
it crosses the network, with the TTL decrementing each time.

### 11.3 Router panel (`/projects/:id/routers/:node_id`)

For each router in the project, a panel showing:

- **Routing table** — `ip route` output, refreshed every 2s
- **ARP table** — `ip neigh` output, refreshed every 2s
- **Interface status** — `ip -br addr` output
- **CPU / memory** — from `psutil` inside the router container
- **Anomaly banner** — appears if an IP's MAC changes between polls

### 11.4 Switch panel (`/projects/:id/switches/:node_id`)

For each switch in the project (deferred from v1 if needed):

- **MAC table** — which MAC is on which port, refreshed every 2s
- **Port status** — which ports are up/down

### 11.5 Hosts view (`/projects/:id/hosts`)

Per-host cards, each showing:

- Hostname, IP, status (online / offline)
- Live CPU / memory (polled from the host's `/metrics` endpoint)
- A "ping" button that runs ping from that host to any other IP
- A "messages" link that opens the per-host message console

### 11.6 Attacks view (M4 phase 06 — `/projects/:id/attacks`)

If an attacker is present, a tab showing:

- A per-attacker card with mode picker, target readout, and Start/Stop
- Live signal timeline (new_mac, arp_rate, syn_rate, http_rate, …)
- Per-mode teaching card (markdown, rendered inline)
- A "Live attack timeline" across all attackers in the project

The detection is server-side: `attack_detector` polls every attacker's
`:9092/state` once per second, compares `packets_per_sec` to per-mode
thresholds, and writes `AttackSignal` rows + broadcasts over WebSocket.
The frontend renders the signals as a live feed; the canvas shows
attackers in an active state with a red ring and a mode pill.

---

## 11a. The dashboard look — every screen in detail

This section shows what the user actually sees on their screen after
they have built and started a project (in this walkthrough, the
example has 3 routers, 3 switches, 10 hosts, and 1 attacker — but the
canvas is just a canvas; the user could have drawn anything). Each
screen is drawn as it would appear in the
browser. Colors are noted inline; the real CSS would use the project's
Tailwind palette.

For reference, the running network is:

```
   [Router-1]──────10.30.99.0/30──────[Router-2]
       │                                   │
       │ 10.30.98.0/30                     │ 10.30.97.0/30
       │                                   │
   [Router-3]                              (nothing)

   Router-1.eth0 (10.30.10.1) ── Switch-1 ── Host-1, Host-2, Host-3, Host-4, Attacker-1
   Router-2.eth0 (10.30.20.1) ── Switch-2 ── Host-5, Host-6
   Router-3.eth0 (10.30.30.1) ── Switch-3 ── Host-7, Host-8, Host-9, Host-10
```

### 11a.1 The projects home (`/projects`)

The landing page. A grid of project cards. The first-time UX
(phase 08) shows a 12-second toast with a **Try the killer demo**
CTA on the empty state; the demo button (`⚡ Killer demo`) is
also always present in the header.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Projects                                              [⚡ Killer demo] [+ New project]
│  Each project is its own network canvas.                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │ 🟢 Lab A        │  │ ⚫ Lab B        │  │ 🟡 Lab C        │              │
│  │ 4 nodes · 3 wir │  │ 5 nodes · 4 wir │  │ 8 nodes · 7 wir │              │
│  │ running         │  │ stopped         │  │ partial         │              │
│  │ 2 min ago       │  │ yesterday       │  │ 3 hours ago     │              │
│  │ [Open canvas][✕]│  │ [Open canvas][✕]│  │ [Open canvas][✕]│              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Status pill colour follows the design-system contract: `running` = green, `partial` = yellow, `starting` = cyan pulse, `stopped` = grey, `error` = red, `draft` = slate
- "Open canvas" takes the user to that project's canvas
- "New project" opens a one-field modal (name only) and lands on the blank canvas
- The first-time killer-demo toast only fires once per browser (see `containernet.killer_demo_toast_shown` in localStorage)

### 11a.2 The canvas (main project view — `/projects/:id/canvas`)

The main view. Everything the user has built, live.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A                     [▶ Start] [⏹ Stop] [💾 Save] [⋯] │
│   🟢 running · 14 containers · 5 links · 1 attacker                        │
├────────────┬─────────────────────────────────────────────────────────────────┤
│            │                                                                  │
│ SIDEBAR    │   CANVAS (React Flow, infinite zoom & pan)                      │
│            │                                                                  │
│ ▸ Canvas ● │        ┌─────────┐                          ┌─────────┐         │
│   Wires    │        │ 📡 R-1  │────10.30.99.0/30────── │ 📡 R-2  │         │
│   Routers  │        │ 10.30.10.1                       │ 10.30.20.1        │
│   Switches │        │ .99.1                            │ .99.2              │
│   Hosts    │        └───┬─────────────┘                  └──┬───────────┘   │
│   Attacks  │            │                                    │               │
│   Comms    │     ┌──────┴──────┐                      ┌──────┴──────┐        │
│   Messages │   10.30.10.0/24  │                      │ 10.30.20.0/24│        │
│   Logs     │            │                              │             │        │
│            │        ┌────┴────┐                    ┌───┴────┐        │        │
│            │        │ 🔀 S-1  │                    │ 🔀 S-2 │        │        │
│            │        │  5 ports│                    │ 2 ports│        │        │
│            │        └─┬──┬──┬─┘                    └─┬───┬──┘        │        │
│            │          │  │  │  │                    │   │             │        │
│            │      ┌───┘  │  │  └───┐                │   │             │        │
│            │      │   ┌──┘  │      │                │   │             │        │
│            │      │   │     │      │                │   │             │        │
│            │   ┌──┴┐ ┌┴──┐ ┌┴──┐ ┌─┴──┐  ┌──┐     ┌┴─┐ ┌┴─┐  ┌──┐   │        │
│            │   │💻H1│ │💻H2│ │💻H3│ │💻H4│  │💣A│     │💻H5│ │💻H6│  ...  │        │
│            │   │.11 │ │.12 │ │.13 │ │.14 │  │.99│     │.11 │ │.12 │       │        │
│            │   └────┘ └────┘ └────┘ └────┘  └──┘     └────┘ └────┘       │        │
│            │      🟢    🟢    🟢    🟢    🔴                              │        │
│            │   (green=up, red skull=attacker)                              │        │
│            │                                                                  │
│            │   ┌─Live activity─────────────────────────────────────────┐   │
│            │   │ ⚡ Host-1 → Host-5  "ping"            12 ms  ✅       │   │
│            │   │ ⚡ Host-2 → Host-7  HTTP "GET /"     143 ms ✅       │   │
│            │   │ 🔴 Attacker-1 → Router-1  ARP spoof   active         │   │
│            │   └────────────────────────────────────────────────────────┘   │
│            │                                                                  │
├────────────┴─────────────────────────────────────────────────────────────────┤
│ FOOTER: status bar — total: 14 nodes, 5 links, 3 routers, 1 attacker       │
└──────────────────────────────────────────────────────────────────────────────┘
```

Notes:
- The **canvas** is a free-form drag-drop area. The user pans with
  right-click drag, zooms with scroll, and can drag nodes around.
- Each node has a **status dot**: green = container up, red = container
  down, gray = stopped. The attacker has a red dot + skull icon.
- The wires are colored by **subnet**. In v1 they can all be the same
  color; in v2 they could be colored by /24 group.
- The **Live activity strip** at the bottom is a tail of the WebSocket
  event stream — every communication, every status change, every
  anomaly. It's a passive feed the user can scroll through.
- The **sidebar** on the left has links to all the other views.

### 11a.3 Clicking a router — the side panel

The user clicks Router-1. A side panel slides in from the right.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A                                              [× Close] │
├────────────────────────────────────────┬─────────────────────────────────────┤
│                                        │  ┌─────────────────────────────┐  │
│            (canvas dimmed)             │  │ 📡 Router-1                 │  │
│                                        │  │ Status: 🟢 running          │  │
│                                        │  │ Container: a3f4b2c1d4e5...  │  │
│                                        │  │ Uptime: 4m 12s              │  │
│                                        │  ├─────────────────────────────┤  │
│                                        │  │ INTERFACES                  │  │
│                                        │  │ ┌─────────────────────────┐ │  │
│                                        │  │ │ eth0  10.30.10.1/24  UP │ │  │
│                                        │  │ │ eth1  10.30.99.1/30  UP │ │  │
│                                        │  │ │ eth2  10.30.98.1/30  UP │ │  │
│                                        │  │ │ [+ add interface]       │ │  │
│                                        │  │ └─────────────────────────┘ │  │
│                                        │  ├─────────────────────────────┤  │
│                                        │  │ STATIC ROUTES               │  │
│                                        │  │ 10.30.20.0/24 via 10.30.99.2│  │
│                                        │  │ 10.30.30.0/24 via 10.30.99.2│  │
│                                        │  │ [+ add route]               │  │
│                                        │  ├─────────────────────────────┤  │
│                                        │  │ [View full panel →]         │  │
│                                        │  └─────────────────────────────┘  │
└────────────────────────────────────────┴─────────────────────────────────────┘
```

There are two ways to look at a router:
- The **side panel** (above) — quick summary, can be edited while the
  project is stopped.
- The **full router panel** (next) — the live diagnostic view.

### 11a.4 The full router panel (`/projects/:id/routers/:nodeId`)

The user clicks "View full panel" or navigates via the sidebar. This is
the most powerful teaching view in the system — it shows the router's
internal state, live.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Router-1                              [⏸ Pause] [↻]  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  📡 Router-1   🟢 running   14s ago      CPU 1.2%   MEM 84 MB   ⏱ 4m 12s  │
│                                                                              │
│  ┌─ TABS ────────────────────────────────────────────────────────────────┐  │
│  │ [Routing] [ARP] [Interfaces] [Stats] [Events]                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ╔═ ROUTING TABLE ════════════════════════════════════════════════════════╗  │
│  ║  Destination        Gateway         Iface   Metric  Proto      Scope  ║  │
│  ║ ─────────────────────────────────────────────────────────────────────  ║  │
│  ║  10.30.10.0/24     —                eth0    0       kernel     link   ║  │
│  ║  10.30.20.0/24     10.30.99.2       eth1    0       static            ║  │
│  ║  10.30.30.0/24     10.30.99.2       eth1    0       static            ║  │
│  ║  10.30.99.0/30     —                eth1    0       kernel     link   ║  │
│  ║  10.30.98.0/30     —                eth2    0       kernel     link   ║  │
│  ║  default           —                —       —       —          —      ║  │
│  ╚════════════════════════════════════════════════════════════════════════╝  │
│                                                                              │
│  ╔═ ARP TABLE ════════════════════════════════════════════════════════════╗  │
│  ║  IP              Iface   MAC                  State        Last seen ║  │
│  ║ ─────────────────────────────────────────────────────────────────────  ║  │
│  ║  10.30.10.11     eth0    02:42:0a:1e:0a:0b   REACHABLE     2s        ║  │
│  ║  10.30.10.12     eth0    02:42:0a:1e:0a:0c   REACHABLE     4s        ║  │
│  ║  10.30.10.13     eth0    02:42:0a:1e:0a:0d   STALE         18s       ║  │
│  ║  10.30.10.14     eth0    02:42:0a:1e:0a:0e   REACHABLE     1s        ║  │
│  ║  10.30.10.99     eth0    02:42:0a:1e:0a:63   REACHABLE     0s   ⚠   ║  │
│  ║  ...                                                                    ║  │
│  ╚════════════════════════════════════════════════════════════════════════╝  │
│                                                                              │
│  ┌─ ⚠ ANOMALY DETECTED ─────────────────────────────────────────────────┐  │
│  │  ARP cache changed for 10.30.10.99 at 14:32:08                       │  │
│  │  Was: 02:42:0a:1e:0a:11  Now: 02:42:0a:1e:0a:63                     │  │
│  │  Possible ARP spoofing from 10.30.10.99 (Attacker-1).               │  │
│  │  [View attacker] [View wire]                                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

This is the **moment of the demo**. The user sees:

1. The **routing table** (the router's "knowledge of the network")
2. The **ARP table** (which MAC is which IP, with a ⚠ on the suspicious row)
3. The **anomaly banner** at the bottom: "ARP cache changed" with the old
   MAC and the new MAC.

The user clicks "View wire" and the screen transitions to the wire view
of the link where the attack is happening.

### 11a.5 The wire view — per-link packet capture

The user clicks "View wire" on the anomaly, OR right-clicks a wire in
the canvas, OR navigates to `/projects/:id/links/:linkId/log`.

This is **Wireshark scoped to one wire** in the user's network.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Wire: 10.30.10.0/24                     [⏸ Pause] │
│   Live · 1423 packets · ● recording                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Tabs:  [Conversations] [Raw packets] [Attackers] [Stats]                    │
│                                                                              │
│  ╔══ CONVERSATIONS (12 active) ══════════════════════════════════════════╗   │
│  ║                                                                     ║   │
│  ║  ▸ TCP  Host-1:52412 → Host-5:8080        9 pkts   12 ms  ✅       ║   │
│  ║  ▸ TCP  Host-2:52413 → Host-7:8080        7 pkts   23 ms  ✅       ║   │
│  ║  ▸ TCP  Host-1:52414 → 10.30.20.11:8080   3 pkts    —     ⏳       ║   │
│  ║  ▸ ARP  Host-1 → "who-has 10.30.10.1?"    2 pkts         ⚠ SPOOF ║   │
│  ║  ▸ ARP  Attacker-1 → "10.30.10.1 is at 02:42:..:63"  4 pkts   🔴  ║   │
│  ║  ...                                                                 ║   │
│  ╚═════════════════════════════════════════════════════════════════════╝   │
│                                                                              │
│  ┌─ SELECTED CONVERSATION ─────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │  TCP  Host-1:52412 (10.30.10.11) → Host-5:8080 (10.30.20.11)       │   │
│  │                                                                     │   │
│  │  Step-by-step packet walk:                                          │   │
│  │                                                                     │   │
│  │  #1  [SYN]      Host-1 → Host-5      TTL 64  on link0 (10.30.10.0/24)│   │
│  │      ▼                                                                │   │
│  │  #2  [SYN,ACK]  Host-5 → Host-1      TTL 64  on link1 (10.30.20.0/24)│   │
│  │      ▲   crossed Router-1 → Router-2                                 │   │
│  │  #3  [ACK]      Host-1 → Host-5      TTL 64  on link0              │   │
│  │  #4  [PSH,ACK]  Host-1 → Host-5      86 B    "GET /api/ping HTTP/1.1" │
│  │      TTL 64  on link0                                               │   │
│  │      ...                                                              │   │
│  │                                                                     │   │
│  │  [Show full L2/L3/L4/L7 breakdown for any step →]                   │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─ ATTACKERS ON THIS WIRE ─────────────────────────────────────────────┐   │
│  │  🔴 Attacker-1  · ARP-spoof Router-1   · 4 pkts/sec   · 14s active │   │
│  │     Last seen packet: 14:32:08.412  "10.30.10.1 is at 02:42:..:63" │   │
│  │     [View attacker] [Stop attack]                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The conversation list at the top shows every TCP conversation on this
wire. The highlighted "ARP" lines in red are the **attacker's spoofed
ARPs** — the user can see them in real time.

Clicking any conversation expands it to show the **full packet walk**:
each packet with its direction, size, TTL, and **which link it appeared
on**. For inter-subnet traffic, the same packet appears in multiple
wire views with the TTL decrementing each time it crosses a router.

### 11a.6 The hosts view (`/projects/:id/hosts`)

A grid of cards, one per host. This is the "host monitor" from the
original system, now per-project.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Hosts                              [⟳ Refresh] [⚙]  │
│   10 hosts · 10 online · 1 attacker                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Filter: [All] [Online] [Offline] [Attackers]      Sort: [Name ▼]           │
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌───────────┐ │
│  │ 💻 Host-1      │  │ 💻 Host-2      │  │ 💻 Host-3      │  │ 💻 Host-4 │ │
│  │ 10.30.10.11    │  │ 10.30.10.12    │  │ 10.30.10.13    │  │ .14       │ │
│  │ 🟢 online      │  │ 🟢 online      │  │ 🟢 online      │  │ 🟢 online │ │
│  │                │  │                │  │                │  │           │ │
│  │ CPU  2%        │  │ CPU  4%        │  │ CPU  1%        │  │ CPU 3%    │ │
│  │ MEM  18%       │  │ MEM  17%       │  │ MEM  19%       │  │ MEM 18%   │ │
│  │ ▁▂▁▂▁▂▁▂      │  │ ▁▁▂▁▁▂▁▁      │  │ ▁▁▁▁▁▁▁▁      │  │ ▁▂▁▁▂▁▂▁ │ │
│  │                │  │                │  │                │  │           │ │
│  │ [Ping ▾] [💬]  │  │ [Ping ▾] [💬]  │  │ [Ping ▾] [💬]  │  │ [Ping ▾]  │ │
│  └────────────────┘  └────────────────┘  └────────────────┘  └───────────┘ │
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐                                      │
│  │ 💣 Attacker-1  │  │ 💻 Host-5      │   ... (scroll for more)              │
│  │ 10.30.10.99    │  │ 10.30.20.11    │                                      │
│  │ 🔴 attacking   │  │ 🟢 online      │                                      │
│  │                │  │                │                                      │
│  │ Mode: arp_spoof│  │ CPU  2%        │                                      │
│  │ Target: R-1    │  │ MEM  18%       │                                      │
│  │ Rate: 4 pps    │  │ ▁▁▁▁▁▁▁▁      │                                      │
│  │                │  │                │                                      │
│  │ [Stop attack]  │  │ [Ping ▾] [💬]  │                                      │
│  └────────────────┘  └────────────────┘                                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Each card has:
- Name + IP + status dot
- Live CPU and memory with a tiny sparkline
- A "Ping" dropdown (the user picks a target IP from a list)
- A "💬" button that opens the per-host message console

The attacker card stands out with the red border and skull icon, and
shows the current attack mode + target + rate.

### 11a.7 The trigger panel — send a communication

The user can trigger a communication from the canvas, the hosts view,
or the dedicated communications page.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Send Communication                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ TRIGGER ────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │   From:    [Host-1  (10.30.10.11)        ▼]                       │   │
│  │   To:      [Host-5  (10.30.20.11)        ▼]                       │   │
│  │   Protocol:[HTTP                          ▼]                        │   │
│  │   Payload: [Hello!_________________________________________]      │   │
│  │                                                                      │   │
│  │   Route preview:                                                     │   │
│  │   Host-1 → Switch-1 → Router-1 → Router-2 → Switch-2 → Host-5      │   │
│  │                                                                      │   │
│  │   [  ▶  SEND  ]                                                      │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─ RECENT COMMUNICATIONS ──────────────────────────────────────────────┐   │
│  │  Time     From     →  To        Proto  Latency   Status             │   │
│  │  ──────────────────────────────────────────────────────────────     │   │
│  │  14:32:08 Host-1   →  Host-5    HTTP    12 ms   ✅ delivered       │   │
│  │  14:31:55 Host-2   →  Host-7    HTTP    23 ms   ✅ delivered       │   │
│  │  14:31:40 Host-1   →  Host-3    HTTP     3 ms   ✅ delivered       │   │
│  │  14:30:12 Host-4   →  Host-9    HTTP    45 ms   ✅ delivered       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The **route preview** is a new addition: the system knows the topology
(it has the link data and the router's static routes), so it can show
the user the path the packet will take before they click Send. This
turns a "fire-and-forget" action into a "let me see the route first"
action.

After Send, the user can:
- Watch the wire views (the packet crosses 3 links: link0, link3, link1)
- See the latency appear in the recent communications list
- See the message appear in both Host-1's (sent) and Host-5's (received)
  message consoles

### 11a.8 The message console — per host

Clicking 💬 on Host-1's card opens Host-1's message console.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Host-1 messages                     [⟳] [🗑 Clear]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Host-1 console ────────────────┬─ Host-5 console ─────────────────────┐ │
│  │                                 │                                       │ │
│  │ 14:32:08 → Host-5              │ 14:32:08 ← Host-1                   │ │
│  │   "Hello!"                     │   "Hello!"                           │ │
│  │   delivered in 12ms            │   received, 12ms                      │ │
│  │                                 │                                       │ │
│  │ 14:31:40 → Host-3              │ 14:31:55 → Host-7                   │ │
│  │   "ping"                       │   "ping"                              │ │
│  │   delivered in 3ms             │   delivered in 23ms                   │ │
│  │                                 │                                       │ │
│  │ 14:30:12 ← Host-4              │ 14:30:00 ← Host-2                   │ │
│  │   "are you up?"                │   "are you up?"                       │ │
│  │   received                     │   received                            │ │
│  │                                 │                                       │ │
│  │ ...                             │ ...                                   │ │
│  │                                 │                                       │ │
│  └─────────────────────────────────┴───────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Outgoing messages (→) are in blue, incoming (←) in green. The console
streams in real time over the WebSocket. The user typically has 2
consoles side by side — the source host and the destination host — so
they can watch both ends of a conversation.

### 11a.9 The attacks view — observing an active attack

`/projects/:id/attacks` — appears in the sidebar only when an attacker
exists. This is the M3 view.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Attacks                              [🛑 Stop all]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Active attackers: 1                                                         │
│                                                                              │
│  ┌─ 💣 Attacker-1 ───────────────────────────────────────────────────────┐  │
│  │                                                                       │  │
│  │  Mode:     ARP spoof                                                  │  │
│  │  Target:   Router-1 (10.30.10.1)                                      │  │
│  │  Link:     10.30.10.0/24                                              │  │
│  │  Running:  14 seconds  ·  Rate: 4 packets/sec                         │  │
│  │  [Stop attack] [View wire]                                            │  │
│  │                                                                       │  │
│  │  ┌── Live signals ────────┬── What this means ──────────────────────┐ │  │
│  │  │                        │                                        │ │  │
│  │  │ ⚠ ARP anomaly         │  The router's ARP cache for            │ │  │
│  │  │   10.30.10.1 was at    │  10.30.10.1 (itself) has been         │ │  │
│  │  │   02:42:..:01          │  overwritten. Hosts sending to         │ │  │
│  │  │   is now at            │  Router-1 are actually sending to     │ │  │
│  │  │   02:42:..:63  🔴     │  the attacker. This is a textbook     │ │  │
│  │  │                        │  MITM setup.                           │ │  │
│  │  │                        │                                        │ │  │
│  │  │ ⚠ Victim hosts: 4     │  4 hosts on the same subnet have       │ │  │
│  │  │   Host-1, Host-2,     │  likely also updated their ARP        │ │  │
│  │  │   Host-3, Host-4      │  caches and are now sending            │ │  │
│  │  │                        │  inter-segment traffic through the     │ │  │
│  │  │                        │  attacker.                             │ │  │
│  │  │                        │                                        │ │  │
│  │  └────────────────────────┴────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  ┌── Detection timeline ──────────────────────────────────────────┐   │  │
│  │  │ 14:32:08  ⚠  ARP cache changed: 10.30.10.1                     │   │  │
│  │  │ 14:32:05  🔴  Attacker started sending gratuitous ARPs          │   │  │
│  │  │ 14:32:00  🟢  Attacker-1 joined the network                    │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The attacks view has **two columns** for each attacker:

- **Left column** = live signals (numbers, alerts, what the system
  observed). Computed from the SSE packet stream + the router ARP polls.
- **Right column** = the lesson (static text explaining what the attack
  means in the context of the TCP/IP layer it abuses).

The detection timeline at the bottom is a chronological log of "what
happened" — useful for post-mortem and for viva explanations.

### 11a.10 The logs view — all events

A chronological feed of everything that happened in the project. Useful
for review and debugging.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ContainerNet › Lab A › Logs                              [⏸] [🗑] [⤓ Export]│
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Filter: [All] [Comms] [Status] [Anomalies] [Attacks]      [Search...]      │
│                                                                              │
│  14:33:12  🟢  Host-1  heartbeat received                                   │
│  14:33:09  ✅  comm  Host-1 → Host-5  delivered (12ms)                     │
│  14:33:05  🟢  Host-2  heartbeat received                                   │
│  14:33:00  ⚠   ANOMALY  Router-1 ARP: 10.30.10.1 MAC changed              │
│  14:32:55  🔴  Attacker-1  gratuitous ARP sent                              │
│  14:32:48  🟢  Host-5  heartbeat received                                   │
│  14:32:40  🟢  Host-1  heartbeat received                                   │
│  14:32:30  🟢  Attacker-1  heartbeat received                               │
│  14:32:20  ✅  comm  Host-2 → Host-7  delivered (23ms)                     │
│  14:32:10  🟢  All hosts online                                             │
│  14:32:00  🟢  Attacker-1  joined the network                                │
│  14:31:55  🟢  Host-7  heartbeat received                                   │
│  14:31:50  🟢  Project started (14 containers, 5 links)                     │
│  ...                                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The user can filter by event type, search by host name or IP, and
export the whole log to a file (for the project report).

### 11a.11 Stop / restart / delete

The top bar has the lifecycle controls. After Start, the project is
**running**. The user can:

- Click **⏹ Stop** → all containers stop, bridges remain, project
  status becomes "stopped", container_ids are preserved.
- Click **▶ Start** again → containers come back up, re-attached to
  the same bridges, with the same IPs and routes.
- Click **⋯ → Delete** → all containers removed, all bridges removed,
  all DB rows deleted, project gone.

The lifecycle is identical to Docker Compose: stop preserves state,
delete is destructive.

### 11a.12 What it looks like during an attack — the whole experience

To make all of this concrete, here's what the user sees when they
trigger the killer demo (ARP spoof Router-1 from Attacker-1):

**t=0** — User right-clicks Attacker-1, picks "Start ARP spoof of
Router-1". A red banner appears on the canvas:

```
┌─ 🔴 LIVE ATTACK ─────────────────────────────────────────────────┐
│  Attacker-1 is now ARP-spoofing Router-1. Open the wire view or   │
│  the router panel to observe. [View wire] [View router]           │
└───────────────────────────────────────────────────────────────────┘
```

**t=1s** — In the wire view for the 10.30.10.0/24 segment, a new line
appears in the conversation list every second: "ARP Attacker-1 →
10.30.10.1 is at 02:42:..:63". Red color.

**t=2s** — The user opens Router-1's panel. The ARP table now shows:

```
  10.30.10.11     eth0    02:42:0a:1e:0a:0b   REACHABLE     2s
  10.30.10.12     eth0    02:42:0a:1e:0a:0c   REACHABLE     3s
  10.30.10.13     eth0    02:42:0a:1e:0a:0d   STALE         18s
  10.30.10.14     eth0    02:42:0a:1e:0a:0e   REACHABLE     1s
  10.30.10.99     eth0    02:42:0a:1e:0a:63   REACHABLE     0s   ⚠
```

The 10.30.10.99 row (Attacker-1) is the suspicious one.

**t=3s** — Host-1 sends a ping to Host-5. In the wire view, the ICMP
echo request goes to MAC `02:42:0a:1e:0a:63` (the attacker's MAC), not
`02:42:0a:1e:0a:01` (the router's real MAC). **The packet is now
flowing through the attacker.**

**t=4s** — The attacker forwards the packet on to the real router.
Host-5 still gets a reply. The victim doesn't know anything is wrong.

**t=5s** — The anomaly banner in the router panel:

```
┌─ ⚠ ANOMALY DETECTED ──────────────────────────────────────────┐
│  ARP cache changed for 10.30.10.99 at 14:32:08               │
│  Was: 02:42:0a:1e:0a:11  Now: 02:42:0a:1e:0a:63             │
│  Possible ARP spoofing from 10.30.10.99 (Attacker-1).        │
│  [View attacker] [View wire]                                  │
└───────────────────────────────────────────────────────────────┘
```

**t=10s** — The user clicks the attacks view. The live signals
column shows "4 victim hosts (Host-1, Host-2, Host-3, Host-4) likely
poisoned." The lesson column explains what just happened and which
layer of the TCP/IP model was abused (Layer 2 — the ARP protocol has
no authentication).

This entire sequence — from clicking "Start attack" to seeing the
anomaly — takes about 5 seconds. It's the **killer demo**.

---

## 12. How attacks work in this world

The attacker is just another node. The user drops it on the canvas,
wires it to a link, configures its IP, and picks an attack mode. The
**attack engine** in the agent runs the chosen scenario.

### 12.1 The attack modes

| # | Mode | What the agent does | What the user sees |
|---|------|---------------------|---------------------|
| 1 | **Sniff** | Captures all traffic on the wire (promiscuous mode) | Wire view: every packet, including other hosts' traffic |
| 2 | **ARP spoof** | Sends gratuitous ARP every 1s: "<target_ip> is at <attacker_mac>" | Other hosts' ARP cache updates. Their traffic now flows through the attacker. The router's `ip neigh` panel shows the MAC change. |
| 3 | **DHCP spoof** | Replies to DHCP discovery with a fake gateway IP | New hosts that join trust the attacker as their gateway. |
| 4 | **TCP flood** | Opens 50 parallel TCP connections to a target per second | Target's CPU spikes. Wire view: flood of SYNs. |
| 5 | **HTTP flood** | Sends N HTTP requests/sec to a target's web server | Server's response time degrades. Wire view: flood of HTTP requests. |

The **most pedagogically striking** is **ARP spoof the router** (mode 2):

1. Attacker joins the 10.30.10.0/24 segment with IP 10.30.10.99
2. Attacker starts sending gratuitous ARPs: "10.30.10.1 is at <attacker-mac>"
3. Other hosts on the segment (Host-1, Host-2, etc.) update their ARP cache
4. The router's view of those hosts' MACs may also get poisoned
5. Now when Host-1 sends a packet to a host on a different segment, it
   goes to the attacker's MAC, not the router's
6. The attacker can read it, then forward it on (so the user doesn't notice)
7. **The dashboard's router panel shows the anomaly in real time**

This is **a real MITM attack, demonstrated on real Docker containers,
visible in the UI without the user having to read a single line of
Wireshark output**. It's the killer demo for any viva or showcase.

### 12.2 The detection is mostly client-side

The dashboard already has the wire view (live packet capture on every
link). The detection code runs **in the browser** over the live packet
stream, using the same `tcpClassifier.ts` pattern from M2.

For the **router ARP anomaly**, the detection is even simpler: the
router's `ip neigh` panel already shows the table. The browser
compares the current snapshot to the previous one and raises a banner
on any change. No new backend work needed.

For the **TCP flood** detection, the browser counts SYN packets per
source IP per second and raises a banner if any IP exceeds a threshold.

For the **HTTP flood** detection, the browser counts HTTP requests per
source IP per second.

All detection runs **over the existing SSE stream** + the existing
router polling. No new backend endpoints are needed for the detection
itself.

---

## 13. Lifecycle: what happens from create to delete

| Phase | User action | Backend does | Database state |
|-------|-------------|--------------|----------------|
| **Create** | Clicks "New Project" | Creates a Project row (status=draft) | 1 row in projects |
| **Edit** | Drags nodes, draws wires, configures IPs | Persists each save | Rows in project_nodes, project_interfaces, project_links |
| **Start** | Clicks Start | Validates → creates bridges → spawns containers → wires them up | All rows get container_ids, project.status=running |
| **Use** | Pings, triggers comms, watches wires | Proxies, captures, broadcasts events | Communications + messages get inserted |
| **Stop** | Clicks Stop | Stops all containers (keeps them on disk) | container_ids preserved, project.status=stopped |
| **Restart** | Clicks Start again | Re-uses existing containers, re-attaches to bridges | container_ids unchanged |
| **Delete** | Clicks Delete | Force-removes containers → removes bridges → deletes DB rows | All rows gone |

The **Stop → Restart** cycle is important: it lets the user pause a
running project (free up CPU) and resume it later with the same
container IDs. This is exactly the model Docker Compose uses.

---

## 14. The networking model in one paragraph

A ContainerNet project is a **graph of nodes connected by links**, where
every link is a real Docker bridge network. Routers are Linux containers
with `ip_forward=1` and a small static routing table. Hosts are Linux
containers with one interface and a default route pointing to the router
on their link. Every link has a capture container that runs tcpdump
and writes structured NDJSON to a file the backend can read. The
backend orchestrates this via the Docker SDK, persists the topology
in PostgreSQL, and exposes REST + WebSocket + SSE to a React frontend
that gives the user a Cisco-Packet-Tracer-style drag-drop editor plus
live views into every router, every wire, and every host.

---

## 15. What this enables academically

Each feature in this system maps to a section of a real networking
textbook. The platform doesn't just demonstrate the concepts — it
gives the user a way to **build, break, and observe** them.

| Textbook concept | ContainerNet demo |
|------------------|-------------------|
| **IP addressing & subnets** | The user picks the IPs on every interface. Wrong choices (overlapping subnets) are caught at Start. |
| **Default gateway** | The system sets the host's default route automatically. The user can see it in the host's `ip route` output. |
| **Static routing** | The user enters static routes on every router. They can watch the routes appear in the router's panel. |
| **ARP & MAC learning** | The router's `ip neigh` panel shows the live ARP table. The user can see entries appear as traffic flows. |
| **Packet forwarding** | The user opens two wire views (before and after a router) and watches the same packet with decremented TTL. |
| **Network segmentation** | The user builds two subnets and watches how inter-subnet traffic must traverse the router. |
| **MITM attack** | The user runs the ARP-spoof attacker and watches traffic reroute through the attacker. |
| **DDoS attack** | The user runs the flood attacker and watches a target's CPU spike. |
| **Defense / detection** | The router's anomaly banner shows the ARP spoof in real time. |

Each of these is a chapter in a project report. The platform provides
the demos to back them up.

---

## 16. Build order (the 9-phase M4 plan)

The system is built in 9 independent, testable phases. Each phase
ends with something the user can see, and the system keeps working
at every phase. The full plan with per-phase acceptance tests lives
in [`phases/milestone-4/`](./phases/milestone-4/overview.md).

| #  | Phase                              | What it adds                                                            | Visible result                                                                  |
|----|------------------------------------|-------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| 01 | Data model + canvas editor         | `ProjectNode`, `ProjectInterface`, `ProjectLink`; React Flow drag-drop | User can build a 3-router network by dragging and dropping                        |
| 02 | Router container + per-wire bridges| `containernet-router-base` + spawn function; one Linux bridge per link  | User can wire routers and see a test topology with one bridge per wire          |
| 03 | Live router panel                  | Streaming `ip route` / `ip neigh` / interfaces; anomaly detection      | User can see what the router knows, in real time                                |
| 04 | Wire view (per-link capture)       | NDJSON capture per link; per-link packet stream with protocol colour     | User can see packets on any specific link                                       |
| 05 | Trigger + message console          | `+ Send` modal; per-host message log                                    | User can fire a real HTTP request across the topology                           |
| 06 | Attacks view                       | Attacker kind + 5 attack modes + detection signals + teaching cards     | User can drop an attacker and watch a real MITM with anomaly signals             |
| 07 | Logs view + lifecycle events       | Per-project event timeline; orphan sweeper; SSE live feed                | User can see every lifecycle, wire, message, anomaly, and attack in one place   |
| 08 | Polish + killer demo               | Error boundary, `?` shortcuts modal, one-click ARP-spoof MITM demo      | First-time user gets a 60-second killer demo with a single click                 |
| 09 | Docs + handoff                     | This doc + Makefile + RUNBOOK + M3 archive                              | A new contributor can clone, build, run, and complete the killer demo unassisted |

**M4 is the new build order.** M1, M2, M3 are history; their
`phases/` folders are kept for reference. The 5 attack scenarios
that were originally M3's scope are now M4 phase 06, built on top
of the M4 routed topology instead of the M3 flat bridge.

---

## 17. What I cut from the ideal version (and why)

The architecture above is the **target**. For a realistic v1 build, the
following are out of scope:

| Cut | Why | When it can come back |
|-----|-----|----------------------|
| Switches as visible nodes | A bridge IS a switch. Rendering it as a node is a visualization choice, not a protocol requirement. | When we want fancy MAC-learning animations |
| MAC table on switches | Same — no protocol behavior | When switches become real (v2) |
| Servers with HTTP | Hosts can already serve HTTP. A "server" kind is just a host with a flag. | When we want curated services (Apache, MySQL) |
| Dynamic routing (BGP/OSPF) | Static routes cover the teaching cases | When we want a "many-router" demo |
| ACLs / firewall on routers | Out of academic scope for a semester project | When we want to teach defense |
| NAT | Out of scope — no internet simulation in v1 | When we want to teach private/public IP |
| IPv6 | Out of scope — ContainerNet's bridges are IPv4 | When we want to teach the dual-stack |
| Multiple attackers per project | One is enough for the demo | When we want a "botnet" demo |
| Topology templates / starter topologies | The user is the engineer. A blank canvas is the only entry point. | Never — adding one would betray the product premise. |

Each of these is named and remembered. None of them blocks the v1 build.

---

## 18. How this connects to what's already in the repo

The repository today has the **first half** of this system built. The
existing files are the foundation; the new ones are the additions.

| Already exists | What it does | Used as |
|----------------|--------------|---------|
| `backend/app/api/projects.py` | CRUD on projects | Becomes a thin wrapper over the new node/link service |
| `backend/app/services/topology_generator.py` | Generated mesh/star/ring/bus/tree | **Removed.** There are no templates. The blank canvas is the only entry point. The only useful leftover — IP allocation helpers — moves into `network_service.py` as a pure function `allocate_ips_for(node_count) -> [str]` with no topology knowledge. |
| `backend/app/services/container_service.py` | Docker SDK wrapper | Extended with `spawn_node()` for all kinds |
| `backend/app/services/packet_service.py` | Reads capture NDJSON | Rewritten to be keyed by link, not by project |
| `backend/app/services/communication_service.py` | Triggers host-to-host messages | Mostly unchanged; the message now traverses routers |
| `host-agent/agent.py` | The agent that runs in every host | Unchanged — the same code runs in hosts and attackers |
| `host-agent/capture_shim.py` | Parses pcap → NDJSON | Unchanged — moved to its own image |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket client | Unchanged |
| `frontend/src/hooks/usePacketStream.ts` | SSE client for packets | Unchanged — but now receives events scoped to a link |
| `frontend/src/components/topology/` | The current topology view | Rewritten as a real React Flow editor |
| `frontend/src/components/message-window/` | Per-host message console | Unchanged |
| `infra/hosts/host-base.Dockerfile` | The host container image | Unchanged — the attacker uses the same image |
| `infra/hosts/capture-base.Dockerfile` | The capture container image | Unchanged |
| `phases/milestone-1/` | M1 design docs | Reference |
| `phases/milestone-2/` | M2 design docs (capture pipeline) | Reference |
| `phases/milestone-3/` | M3 design docs (attacker scenarios) | Updated to reflect the router-aware attacks |

The **new** files are:
- `backend/app/models/project_node.py` (or replace `project_host.py`)
- `backend/app/models/project_interface.py` (new)
- `backend/app/models/project_link.py` (replaces `project_edge.py`)
- `backend/app/models/project_capture.py` (new)
- `backend/app/services/node_service.py` (new)
- `backend/app/services/link_service.py` (new)
- `backend/app/services/router_proxy.py` (new)
- `backend/app/services/bridge_service.py` (new — or merged into `container_service.py`)
- `router-agent/router_agent.py` (new)
- `switch-agent/switch_agent.py` (new — but optional in v1)
- `infra/hosts/router-base.Dockerfile` (new)
- `infra/hosts/switch-base.Dockerfile` (new — optional in v1)
- `frontend/src/components/canvas/` (new — the React Flow editor)
- `frontend/src/components/wire-view/` (new — the per-link capture view)
- `frontend/src/components/router-panel/` (new — the live router widget)

That's about 15 new files for the backend + frontend, plus the schema
migration. The rest of the system is reused.

---

## 19. The single most important thing

If you take one thing away from this document, it's this:

> **ContainerNet is a visual network editor backed by real Docker
> containers. The user is a network engineer. They drag, they wire,
> they click Start, and they get a real network with real packets they
> can watch. Every abstraction in the system — node, interface, link,
> bridge, capture, router — exists to map the user's mental model
> onto Docker primitives.**

When in doubt about any design decision, ask: **"What would the user
see in Cisco Packet Tracer?"** The answer is the right answer.

---

*This document is the architectural target. The current state of the
codebase is the v1 + parts of M2 + the start of M3. The roadmap for
the remaining work lives in `phases/milestone-3/overview.md` and (to
be written) `phases/milestone-4/overview.md`.*
