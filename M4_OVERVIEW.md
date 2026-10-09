# Milestone 4 — Overview (Shipped)

> **Status:** ✅ Complete (all 9 phases shipped, accepted, on `main`)
> **Goal:** Turn ContainerNet from a flat-host LAN into a full
>           **Docker-based virtual network lab**. The user opens a
>           blank canvas, drags routers / hosts / attackers onto it,
>           wires them up, types IPs, clicks **Start**, and the
>           backend materializes one Docker container per node and
>           one Linux bridge per wire. Every screen of the dashboard
>           is built against a single, deliberate **dark design
>           system** so the product looks like a real network tool.

This file describes what was actually built, how it fits together,
and how each piece works in detail. It is the **post-build** counterpart
to `phase_m4-00_overview.md` (the original pre-build scope doc); read
that first if you want to see what was *planned* versus this file's
description of what was *delivered*.

---

## 0. The one rule that survived every phase

**There are no templates. The canvas is always blank.** No "3 offices"
preset. No "home LAN" starter. No "two-router example." The user is the
network engineer. The system is a faithful Docker materialization of
whatever they draw. The single concession shipped after the fact: the
**Killer demo** button on the projects home — that is a *project the
backend creates programmatically* on first launch, not a UI template.
The user can still open a blank canvas and start from scratch.

---

## 1. The product in one paragraph

The user opens `http://localhost:5173`. The **Projects** page is a grid
of the projects they have built (the Killer demo is there too). They
click **+ New project**. A blank **Canvas** opens with a left-side
toolbox (host, router, attacker — switch and server entries are
temporarily hidden, see §5.4). They drag a router onto the canvas,
drag two hosts, drag one attacker, draw wires between them,
double-click each node to type its IPs, click **Save**, click
**Start**. The backend materializes everything: one Docker container
per node, one Linux bridge per wire. The canvas now shows live green
dots on every node and neon-colored lines on every wire. The user
clicks the router → sees its live `ip route` and `ip neigh` tables.
Clicks a wire → sees a real-time `tcpdump`-style feed of every frame
on that bridge. Opens the **Send** modal on a host, picks another
host, sees the resolved route ("Host-1 → Router-1 → Router-2 →
Host-5") before clicking Send, then watches the packet cross three
wire views in real time. Adds an attacker, picks ARP spoof, clicks
Start, watches the router's `ip neigh` table visibly corrupt. They
were the engineer. The system is the workbench.

---

## 2. The 5-primitive data model (what every screen agrees on)

M4 replaced M2's flat `ProjectHost` + `ProjectEdge` model with a true
5-primitive model that mirrors a packet-tracer's mental model:

| # | Primitive | DB table | What it is |
|---|---|---|---|
| 1 | **Project** | `projects` | The whole network the user is building. Has a `status` (`draft` / `starting` / `running` / `stopping` / `stopped` / `error`). |
| 2 | **Node** | `project_nodes` | A device on the canvas. `kind ∈ {host, switch, router, server, attacker}`. Carries `canvas_x`, `canvas_y`, `attack_mode` (nullable, attacker-only). |
| 3 | **Interface** | `project_interfaces` | A port on a node. Has `name` (user-typed label like `eth0` / `Gi0/0/0`), `ip_address` (nullable for switch ports), `subnet_mask` (e.g. `/24`). Routers can have many. |
| 4 | **Link** | `project_links` | A wire between two interfaces. Both ends share a `subnet_cidr` (auto-derived). Maps 1:1 to a Docker bridge. Carries `subnet_color_index` (1-6 for wire color), `docker_bridge_name`, `docker_network_id`. |
| 5 | **Capture** | `project_captures` | The per-link passive sniffer state. One row per link. Tracks `last_packet_at`, `packet_count`. |

Auxiliary tables added in M4:
- `anomaly_events` — rows written by the router anomaly poller when
  a router's `ip neigh` shows a MAC change for a known IP
  (M4-03).
- `attack_signals` — rows written by the attack detector when an
  attacker's self-reported `packets_per_sec` crosses a per-mode
  threshold (M4-06).
- `communications` — every Send from the Trigger panel / message
  console; carries `comm_id`, src/dst, `protocol`, `payload`,
  `status`, `hops_count` (M4-05).
- `project_events` — the unified log timeline (M4-07).
  `kind ∈ {lifecycle, node_started, node_stopped, bridge_created,
  message_sent, error}`. Single source of truth for the LogsView.

A **subnet** is *not* a primitive. It is the set of interfaces that
share a `subnet_cidr`. The UI colors a wire by its
`subnet_color_index`; the database has no `subnets` table.

**Attacker** is a `host` node with `attack_mode` set on the
`project_node` row and `AGENT_ROLE=attacker` plus `ATTACK_MODE=<m>`
in the container env. The same `host-agent` image runs in both roles;
only the env var and which scripts are enabled differ.

---

## 3. The 9 phases — what each one shipped

| # | Phase | What got built | Where it lives |
|---|---|---|---|
| 01 | Data model + canvas editor | DB migration (5 tables), full REST API, blank React Flow canvas, drag-from-toolbox, drag-to-move, undo/redo, viewport persistence. | `backend/app/api/projects.py`, `backend/app/models/*.py`, `frontend/src/canvas/*` |
| 02 | Router container + per-wire bridges | `host-agent` extended with `AGENT_ROLE`; per-link `cn<8hex>p<4hex>l<4hex>` Docker bridges; `node_service.spawn_node()` for all 5 kinds; the veth-per-wire attach loop. | `backend/app/services/{link,node,container,project_lifecycle}_service.py`, `infra/hosts/*` |
| 03 | Live router panel | Router agent HTTP server on `:9090`, `router_proxy` polled every 2s, `ip route` / `ip neigh` / `ip -br addr` tables in the side panel, anomaly detection on MAC change. | `backend/app/services/{router_proxy,anomaly_detector}.py`, `host-agent/{agent,config}.py`, `frontend/src/panels/RouterPanel.tsx` |
| 04 | Wire view (per link) | Per-link `tcpdump -enni <iface> -U` running inside each node container, writing to `/var/lib/containernet/captures/<proj8>l<link4>.ndjson`, SSE stream tails that file, wire-view UI with conversation / raw / attackers tabs, the 6-color protocol palette. | `backend/app/services/packet_service.py`, `frontend/src/wire-view/*` |
| 05 | Trigger + message console | Trigger modal (HTTP/ping/TCP), `route_resolver` walks the topology, per-host message console with send/receive bubbles, `communication_service` is the only place the backend initiates a message. | `backend/app/services/{route_resolver,communication_service}.py`, `frontend/src/{trigger,messages}/*` |
| 06 | Attacks view | 5 attack modes (`unknown_host`, `duplicate_ip`, `arp_spoof`, `tcp_flood`, `http_flood`), attacker agent HTTP server on `:9092`, `attack_detector` polls every 1s, signals on threshold, teaching cards per mode, canvas red ring + "attacking" pill on the attacker node. | `backend/app/services/{attack_detector,attack_proxy}.py`, `host-agent/{attack_engine,attack_control}.py`, `frontend/src/attacks/*` |
| 07 | Logs view + lifecycle events | `event_service` writes every start / stop / node / bridge / message / error to `project_events`, LogsView renders a chronological filterable timeline, the **orphan sweeper** runs every 60s and cleans up containers + bridges for projects that aren't `running`. | `backend/app/services/{event_service,orphan_sweeper}.py`, `frontend/src/logs/*` |
| 08 | Polish + killer demo | Empty states, loading skeletons, error toasts, error boundary, keyboard shortcuts, first-time UX (auto-creates a demo project on launch), the **Killer demo** button on the projects home that creates a pre-wired ARP-spoof MITM lab and auto-starts it. | `backend/app/services/project_lifecycle.py` (demo project bootstrap), `frontend/src/pages/*`, `frontend/src/components/*` |
| 09 | Docs + handoff | `architecture.md` updated to reflect M4 reality, `README.md` rewritten, `RUNBOOK.md` (11 sections of triage), `Makefile` (`make up / down / build / logs / test / lint / clean`), `phases/milestone-3/` archived. | `architecture.md`, `README.md`, `RUNBOOK.md`, `Makefile`, `phases/archive/milestone-3/` |

Each phase has a self-test in `tests/manual/` and an acceptance doc
in this folder (`PHASE_01_ACCEPTANCE.md`, `PHASE_09_ACCEPTANCE.md`).
The Killer demo (M4-08) is verified end-to-end by
`tests/manual/test_killer_demo.py`: 4/4 containers up, project
`running`, events emitted in order, ARP-spoof visible on the router
panel within 10s.

---

## 4. The full request lifecycle — how a Send actually works

This is the canonical end-to-end flow. It is what every M4-05+
phase was building toward.

### Step 1 — the user opens the Send modal

Frontend (`frontend/src/trigger/SendModal.tsx`) calls
`GET /api/projects/<pid>/route?src=<src_id>&dst=<ip>` on every
keystroke in the destination IP field. The backend's
`route_resolver.resolve_route()` runs against the project's
topology and returns the canonical hop list.

### Step 2 — `route_resolver` walks the topology

`backend/app/services/route_resolver.py`:

1. Loads the project with `nodes.interfaces` and `links` eagerly
   joined.
2. Builds an adjacency map: `node_id → [(neighbor, link, my_iface, peer_iface)]`.
3. Builds a per-node list of "directly attached subnets" (the LPM
   table the walker uses to decide "is dst on my own wire?").
4. For every router node, fetches the **live routing table** from
   the agent via `router_proxy.get_router_state()` (cached 2s).
   Each route is stored as `(network, gateway, dev)` — the gateway
   is the `via` IP, the dev is the kernel-resolved interface name.
5. Walks from the source node: at each step, check if dst is on a
   directly-attached subnet (if yes, return the hop list); else
   pick the egress link. For non-routers, egress is the link whose
   subnet contains dst (with a default-gateway fallback to any
   router neighbor). For routers, **longest-prefix match** against
   the static-routes table, then **match the route's gateway IP
   against the peer's iface IP** on each adjacent link to pick the
   egress link (this is the M4-09 fix — the kernel-assigned
   interface name doesn't match the project-model name, so we
   match by gateway IP instead).
6. Switches are walked through (no L3 decision); the loop is
   capped at `MAX_HOPS = 16` and raises `RouteLoop` past that
   (rendered as a "Routing loop detected" warning).

The response is a list of `Hop` objects
(`{node_id, node_name, node_kind, iface_name, iface_ip, link_id,
link_subnet}`) that the canvas highlights in the wire view after
the message is sent.

### Step 3 — the user clicks Send

The frontend posts to `POST /api/projects/<pid>/messages` with
`{src_node_id, dst_ip, protocol, payload, dst_node_id?}`. This
lands in `communication_service.send_message()`.

### Step 4 — the backend dispatches the message

`backend/app/services/communication_service.py`:

1. Validates that `src_node_id` is a host / server / attacker
   (routers don't initiate; only terminate).
2. Re-resolves the route (so the response and the WS broadcast
   share one canonical hop list).
3. Looks up the source host's IP on the **backend network**
   (`containernet_containernet_lan`), not its topology IP —
   because the backend container can only reach the node via the
   shared backend network. Falls back to the first topology IP
   if the container isn't reachable.
4. POSTs to the source host's `:8080/send` with the body
   `{comm_id, project_id, target_ip, target_host_id, payload, protocol}`.
5. The host-agent's `message_service` opens a NEW HTTP connection
   to `<dst_ip>:8080/receive` and reports back. The backend times
   out after 10s.
6. Persists a `Communication` row (`comm_id`, status, hops_count,
   delivered_at).
7. Broadcasts a `message` event on the project WebSocket
   (`backend/app/services/realtime.py`) so the wire view can
   highlight the hops and the message console can render the
   bubble in real time.
8. Writes a `message_sent` row to `project_events` (M4-07) so
   the LogsView shows the same send in its timeline.

### Step 5 — the agents carry the bytes

The source host-agent's `message_service` is what actually opens
the TCP connection to the destination. It writes the payload to
the kernel via a normal `socket.connect((dst_ip, 8080))` — the
Linux kernel handles the routing, ARP, and forwarding. If the
destination is on a different subnet, the kernel sends the packet
to the default gateway; if that's a router container, the router
forwards per its routing table (which `route_installer` populated
at start time). At the other end, the destination host's
`message_service` accepts the HTTP connection on `:8080/receive`
and returns 200.

### Step 6 — the user sees the result

The frontend's `realtimeStore` ingests the `message` event:
- The message console shows a delivered / failed bubble with the
  payload and the round-trip time.
- The wire view highlights every `link_id` in `hops_crossed` for
  2s, so the user can see the path light up.
- The LogsView shows a `message_sent` row in the same timeline as
  lifecycle events.

---

## 5. How the backend materializes a project (the Start flow)

`backend/app/services/project_lifecycle.py:start_project()` is the
orchestrator. The state machine on `projects.status` is:

```
draft    ──start──▶  starting ──ok──▶  running
                                ──fail─▶  error
running  ──stop──▶   stopping ──ok──▶  stopped
stopped  ──start──▶  starting ──ok──▶  running
partial  ──start──▶  starting  (idempotent resume)
error    ──start──▶  starting  (retry from where we left off)
```

The flow is **idempotent and resumable** — calling Start twice is a
no-op if every container + bridge already exists, and calling Start
after a partial crash re-creates whatever's missing.

### 5.1 Bridges first

For every link, `link_service.create_bridge_for_link()` creates a
Linux bridge named `cn<8hex>p<4hex>l<4hex>` (8-char project prefix +
4-char link prefix; the rest of the 20-char name is the
container-net marker). The bridge's subnet is auto-derived from the
two endpoint IPs by `link_service._derive_subnet()`:

- If both endpoints have the same mask and the IPs are in the same
  network, that network is the bridge subnet.
- Otherwise (mismatched masks, one endpoint has no IP, etc.) we
  fall back to a deterministic `10.250.{hi}.{lo}/30` so the bridge
  is always valid.

The chosen `bridge.short_name` and `bridge.network_id` are
persisted on the `project_links` row so the capture / router
proxy can find them later without re-deriving. A `bridge_created`
event is emitted to `project_events`.

### 5.2 Capture sentinel

For every link, we mark the `project_captures` row as `running`
with `container_id = "node-driven:<proj8>:<link4>"` — a sentinel
meaning "the actual tcpdump processes are distributed across the
node containers, not in a sidecar." This is the M4-04 change:
Linux bridges' fast-forward path bypasses AF_PACKET, so a
sidecar tcpdump on the bridge itself never sees host↔host
unicast. The node's veth, in the node's own netns, sees every
frame that crosses the link. The frontend treats any non-null
`container_id` as "capturing"; the actual NDJSON file is the
source of truth for the SSE stream.

### 5.3 Nodes — routers first, then everything else

Nodes are spawned in this order: routers → switches → everything
else. Routers are up first so any host that needs them as a
default gateway has them ready.

`node_service.spawn_node()` is the single function that
materializes any of the 5 node kinds. It:
1. Picks the image: routers use `infra/routers/router-base`, hosts
   + attackers use `infra/hosts/host-base`, switches + servers
   use `host-base` too (they're hosts with different roles).
2. Sets the env vars:
   - `AGENT_ROLE` ∈ {`host`, `router`, `attacker`}
   - `ATTACK_MODE` (attacker only, e.g. `arp_spoof`)
   - `BACKEND_URL` so the agent can phone home
3. Sets up port mappings:
   - `:8080` (host-agent message service) for host / server /
     attacker
   - `:9090` (router-agent state) for routers
   - `:9092` (attack-control) for attackers
   - `:9100` (Prometheus metrics) for everyone
4. Attaches every `cn<8hex>p<4hex>l<4hex>` bridge the node's
   interfaces touch — the kernel-assigned veth names (`eth0`,
   `eth1`, `eth2` in attach order) are what the agent sees.
5. Assigns the IP from the project model to the right veth.
6. Starts a `tcpdump -enni <iface> -U` per attached link, writing
   to `/var/lib/containernet/captures/<proj8>l<link4>.ndjson`.
7. Starts the agent (host / router / attack) as the container's
   PID 1.

The container id is persisted on the `project_nodes` row, a
`node_started` event is emitted, and we move to the next node.

### 5.4 Status → running, then route install, then detectors

On the last node's success, `project.status` flips to
`ProjectStatus.RUNNING` and a `lifecycle` event fires. Then, in
order:

1. `anomaly_detector.start_polling(project_id)` — starts a
   per-project task that polls every router's `/state` every 2s
   and writes `AnomalyEvent` rows on MAC-change detection.
2. `attack_detector.start_polling(project_id)` — same shape, but
   for attackers, polling `:9092/state` every 1s and writing
   `AttackSignal` rows on threshold breach.
3. `route_installer.install_inter_router_routes(project)` — the
   M4-09 multi-router fix. Walks the topology, finds every
   router-to-router link, waits up to 5s for each router's agent
   to be reachable, then installs the static routes
   (`ip route replace <peer_lan> via <peer_uplink_ip>`) into each
   router's kernel table. **The kernel can auto-pick the outgoing
   interface from a directly-attached next-hop**, so we don't
   need to send `dev=`. The installer retries each `set_route`
   call up to 3 times (500ms backoff) because the first attempt
   right after spawn often hits `Connection refused` while the
   agent's aiohttp server is still binding `:9090`. Failures are
   logged and counted but never abort Start — the project still
   comes up `running`, and the user can fix individual routes
   via the router panel.

### 5.5 Failure rollback

If any bridge or node fails, `_set_error()`:
1. Flips `projects.status` to `error`.
2. Emits an `error (<op>)` lifecycle event with the captured
   errors.
3. Best-effort rollback: stops + removes every node container
   that was started, deletes every bridge that was created, and
   clears `container_id` + `docker_bridge_name` so the next Start
   starts from a clean slate.

### 5.6 The orphan sweeper (the safety net)

`backend/app/services/orphan_sweeper.py` runs every 60s. It does
two passes:

1. **Container pass** — lists every container with the
   `containernet.host=true` label, decodes the owning project
   from the `containernet.project=<pid>` label, and stops +
   removes the container if its project isn't in the `RUNNING`
   set. This catches "backend crashed mid-start" containers.
2. **Bridge pass** — lists every Docker network whose name
   starts with `cn` (our per-wire bridge prefix), decodes the
   project id from the 8-char prefix, and removes the bridge
   if its project isn't RUNNING. This catches the M4-09
   "Pool overlaps" failure where a previous Start created a
   bridge but the project never reached RUNNING (Docker refuses
   to create a bridge with an already-used subnet).

The sweeper is conservative: it never touches a container or
bridge whose project is alive and RUNNING. First sweep is
delayed by 30s after backend startup so a fresh backend has a
chance to register its projects before the first pass.

---

## 6. How the live router panel works (M4-03 + M4-09)

When the user clicks a router node, `RouterPanel` opens. It
displays three live tables:
- `ip -br addr` — interfaces + IPs (refreshed every 2s)
- `ip route` — kernel routing table
- `ip neigh` — ARP / neighbor cache

The backend's `router_proxy` is the only thing that talks to the
router. It opens an aiohttp session and GETs
`http://<backend_lan_ip>:9090/state` on the router agent. The
agent runs `aiohttp` on `:9090` inside the container and
responds with:

```json
{
  "interfaces": [{"name": "eth0", "ip": "10.0.10.1/24", "mac": "..."}, ...],
  "routes":    [{"destination": "192.168.20.0/24",
                "gateway": "10.10.10.2",
                "iface": "eth1"}, ...],
  "neighbors": [{"ip": "10.0.10.10", "mac": "aa:bb:cc:dd:ee:ff", "state": "REACHABLE"}]
}
```

`router_proxy` is cached for 2s per router (to keep the
anomaly poller cheap). The agent's `state` endpoint is fast —
it reads `/proc/net/route` + `/proc/net/arp` + `ip -br addr`
once and returns.

The **anomaly detector** (`backend/app/services/anomaly_detector.py`)
runs a per-project task that polls every router every 2s and
compares the neighbors list to a per-IP last-seen-MAC map. When
the MAC for a known IP changes (the classic ARP-spoof signal),
it writes an `AnomalyEvent` row and broadcasts
`{type: "anomaly", signal: "mac_changed", ...}` over the
project WebSocket. The frontend's `RouterPanel` shows a red
banner on the affected router.

---

## 7. How the wire view works (M4-04)

When the user clicks a wire, `WireView` opens. It subscribes to
the per-link SSE stream `GET /api/projects/<pid>/links/<link_id>/packets/stream`.

The stream tails
`/var/lib/containernet/captures/<proj8>l<link4>.ndjson` line by
line. Each NDJSON line is one packet that crossed the bridge,
tagged by the node-side tcpdump with the kernel interface name,
timestamp, src/dst MAC, src/dst IP, protocol, and (for IP) the
src_node_kind (so the UI can color attack packets).

The wire view has three tabs:
- **Conversation** — groups packets by 5-tuple (proto, src_ip,
  src_port, dst_ip, dst_port), one row per conversation, click
  to drill in.
- **Raw** — every packet, newest first, with the 6-color
  protocol palette (tcp cyan, udp violet, icmp emerald, arp
  amber, http sky, **attack rose**).
- **Attackers** — filtered to packets with `src_node_kind ==
  "attacker"`, so the user can see exactly what the attacker is
  doing on the wire.

The wire view highlights every `link_id` in a Send's
`hops_crossed` list for 2s after the message is sent, so the
user can see the path light up in real time.

---

## 8. How the attacks view works (M4-06)

The attacker container is a host with `AGENT_ROLE=attacker` and
`ATTACK_MODE=<mode>` set. The host-agent's `attack_engine.py`
runs the selected mode in a background thread:

- `unknown_host` — passive; just sits on the bridge with a MAC
  the router has never seen.
- `duplicate_ip` — runs `ip addr add <victim_ip> dev eth0` to
  claim the victim's IP.
- `arp_spoof` — scapy `sendp(ARP(op=2, psrc=<victim>, hwdst=<gw>))`
  every 1s.
- `tcp_flood` — 50 parallel aiohttp connections to the victim.
- `http_flood` — 500 aiohttp POSTs/sec to the victim.

The thread updates `engine.stats` under a lock with
`{running, mode, target_ip, packets_sent, started_at,
last_tick}`. `packets_per_sec` is the per-tick delta.

The `attack_control` HTTP server (aiohttp on `:9092`) exposes:
- `GET /state` — snapshot of `engine.stats`
- `POST /attack` — `{mode, target_ip}` → calls `engine.start()`
- `POST /attack/stop` — `engine.stop()`

The backend's `attack_proxy` is the only thing that talks to
`:9092`. `attack_detector.start_polling(project_id)` runs a
per-project task that polls every attacker every 1s. When
`packets_per_sec > threshold` for a given mode, it writes an
`AttackSignal` row and broadcasts
`{type: "attack_signal", signal_kind, value, threshold, ...}`.

The frontend's `AttacksView` (per-project) and `AttackerPanel`
(per-node) consume those events:
- The attacker node gets a red `shadow-glow-danger` ring + a
  `status-pill-danger` "attacking <mode>" pill while active.
- The signal feed shows the last 50 signals per attacker.
- The teaching card (markdown in `frontend/src/attacks/lessons/`)
  explains the mode: what it does, why it works, the signal
  that fires, and the defence.

---

## 9. How the logs view works (M4-07)

`backend/app/services/event_service.py` is the only writer to
`project_events`. Every other service calls into it:

- `project_lifecycle.start_project()` → `lifecycle` (state
  transitions), `bridge_created` (per link), `node_started` /
  `node_stopped` (per node), `error` (on failure)
- `communication_service.send_message()` → `message_sent` (per
  Send)
- `anomaly_detector` → `anomaly` (per detected event)
- `attack_detector` → `attack_signal` (per threshold breach)

The `LogsView` (`frontend/src/logs/`) is a single chronological
feed filterable by `kind`. It polls `GET
/api/projects/<pid>/events?kind=<k>&since=<ts>` every 2s — no
WebSocket dependency, so it works in the same tab as everything
else without contention.

The orphan sweeper (§5.6) is also part of M4-07: it makes the
"backend crashed mid-start" case recoverable, which is what the
M4-09 fixes to `route_installer` are layered on top of.

---

## 10. How the killer demo works (M4-08)

On the first launch with an empty database, `project_lifecycle`
auto-creates a project named "Killer demo" with this topology:

```
Attacker ──┐
           │
Host-1 ─── Router-1 ─── Host-2
```

(The original M4-08 spec called for a switch; the current
shipping version uses a direct host-to-router topology. Switches
are visually rendered, functionally transparent, and their
toolbox entry is currently hidden — see §11.4.)

The killer demo's `attack_mode` on the attacker is `arp_spoof`.
The **Killer demo** button on the projects home
(`/projects`) calls `POST /api/projects/<demo_id>/start` — the
lifecycle materializes everything, `route_installer` has nothing
to do (single router), and within ~5s the project is `running`
and the attacker has begun gratuitous ARPs. Clicking the
attacker node shows `attack_mode: arp_spoof`; clicking the
router shows its `ip neigh` table visibly corrupting within
10s. The whole demo is one click.

`tests/manual/test_killer_demo.py` verifies this end-to-end
(4/4 containers up, `running`, all events in order).

---

## 11. UI states + the design system

The design system is the single source of truth for every visual
decision in M4. The full spec is in `design-system.md`; the
key contracts are:

### 11.1 Palette

The dark palette is the only palette. There is no light mode,
no theme toggle. The tokens (defined as Tailwind classes via
`frontend/tailwind.config.js`):

| Token | Used for |
|---|---|
| `bg-bg-base` / `bg-bg-surface` / `bg-bg-surface-2` | The three surface levels |
| `border` / `border-strong` | 1px dividers |
| `text-primary` / `text-secondary` / `text-muted` | Three text levels |
| `accent` (cyan), `success` (emerald), `warn` (amber), `danger` (rose), `info` (indigo) | Status |
| `subnet-1` through `subnet-6` | Wire colors (cycled) |
| `protocol-tcp` / `udp` / `icmp` / `arp` / `http` / `attack` | Wire-view protocol colors |

### 11.2 Typography

Single family — Inter for UI chrome, JetBrains Mono for IPs,
MACs, ports, packet hex, and `ip route` output. The wire view's
mono rows are what makes a packet capture actually readable.

### 11.3 Node icons (Cisco-flavored, custom SVG)

Host = monitor, Switch = box with arrows, Router = cylinder,
Server = rack, Attacker = hooded figure. The lit detail (the
monitor's screen, the cylinder's top oval, the attacker's
eyes) is the `accent` cyan so the active node is obvious.

### 11.4 Toolbox state

The current toolbox shows only **Host**, **Router**, and
**Attacker**. The **Switch** and **Server** entries are
temporarily hidden from the UI (commit `c20fe99`) — the
underlying `NodeKind` and full project-model support for them
still exist, so any project that contains switch / server nodes
keeps loading and working. The reason for the hide: the design
is iterating on the canonical 3-primitive teaching topology
(host + router + attacker) and the extra entries cluttered the
toolbox without adding to the demo. They will be re-enabled
in a later phase by re-adding the two entries to `KIND_META`
in `frontend/src/canvas/Toolbox.tsx`.

### 11.5 Empty / loading / error states

Every screen has a deliberate empty state, a loading skeleton
(no spinners — the app is a network tool, not a consumer app),
and an error toast. The error boundary in
`frontend/src/components/ErrorBoundary.tsx` catches uncaught
React errors and shows a friendly "something broke" card with a
reload button instead of a white screen.

### 11.6 Keyboard shortcuts

`?` opens the keyboard shortcut help; `Del` / `Backspace`
deletes the selected node; `Esc` closes the active modal;
`Ctrl+Z` / `Ctrl+Shift+Z` are undo / redo on the canvas.

---

## 12. How to read the rest of the docs

| If you want to... | Read this |
|---|---|
| Understand the system in 15 minutes | `architecture.md` (repo root) |
| Understand M4 in 5 minutes | This file (you are here) |
| See the visual language | `design-system.md` (this folder) |
| Debug a runtime issue | `RUNBOOK.md` (repo root) |
| Run the project | `README.md` + `make up` |
| See the per-phase plan | `phase_m4-01_*.md` through `phase_m4-09_*.md` (this folder) |
| See the per-phase acceptance | `PHASE_01_ACCEPTANCE.md`, `PHASE_09_ACCEPTANCE.md` (this folder) |
| See the manual end-to-end tests | `tests/manual/*.py` |
| See the original pre-build scope | `phase_m4-00_overview.md` (this folder) |

---

## 13. What is explicitly out of scope (deferred to M5+)

These are documented in `architecture.md` §17 and were
intentionally not built in M4:

- **VLANs** — the switch becomes a real multi-VLAN bridge.
- **Dynamic routing** (BGP / OSPF) — for now, multi-router
  topologies rely on `route_installer` to push static routes.
- **NAT** / private-to-public translation.
- **IPv6** — everything is IPv4.
- **Multiple attackers per project** — the data model allows
  it; the UI / detectors are written for N but the killer demo
  has 1.
- **Light theme** — dark only, deliberately.
- **Real switch with MAC-learning table** — switches remain
  visually rendered, functionally transparent. A Linux bridge
  is a perfectly good L2 switch for our purposes; we don't
  need a CAM table on top.
- **Server image with curated services** (Apache, MySQL) — the
  host image with `python -m http.server` is enough for M4.
- **Per-mode attack customization** (rate, target selection) —
  the 5 modes ship with hard-coded parameters; the API supports
  extending them.

These cuts are deliberate and were trade-off decisions, not
oversights. They are documented so future contributors don't
add them as a "small extra."
