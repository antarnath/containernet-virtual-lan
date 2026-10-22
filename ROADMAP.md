# ContainerNet — Roadmap

> **A blank-canvas network lab in your browser** — what's next after Milestone 4.

This document is the post-M4 roadmap. M4 (the 9 phases already shipped) is
the **platform**: blank canvas, 5-primitive data model, one container per
node, one bridge per wire, live router / wire / attack / log views, the
Killer demo, and full docs. M4 ships static IP assignment only — every
address, mask, and route is typed by the user.

This roadmap groups everything you can add next into 20 themed sections.
Each entry has an effort estimate (in working days for one focused
contributor) and a teaching-value tag:

- **Massive** — touches the central concept a class needs to teach
- **High** — most classes want this
- **Medium** — niche but real
- **Low** — nice to have

If you only have time for 10, see the **Top-10 Picks** at the bottom.

---

## 0. Where M4 stops

Before reading the list, recall what M4 ships:

- ✅ Blank canvas, drag-from-toolbox, undo/redo, viewport persistence
- ✅ 5-primitive model (Project / Node / Interface / Link / Capture)
- ✅ One container per node, one Linux bridge per wire (`cn<8hex>p<4hex>l<4hex>`)
- ✅ Routers run `net.ipv4.ip_forward=1`; kernel does L3 forwarding
- ✅ Static routes (manually configured + auto-installed by `route_installer`)
- ✅ Live `ip route` / `ip neigh` / `ip -br addr` on the router panel
- ✅ Per-link `tcpdump` writing NDJSON, SSE stream to the wire view
- ✅ 5 attack modes (unknown_host, duplicate_ip, arp_spoof, tcp_flood, http_flood)
- ✅ Per-project messages via host-agent aiohttp
- ✅ Logs view with the orphan sweeper
- ✅ Killer demo (one-click ARP-spoof MITM)
- ❌ **All IP addresses are typed by the user** (no DHCP)
- ❌ No NAT, no ACLs, no dynamic routing, no VLANs, no IPv6, no CLI
- ❌ Switch is a transparent bridge (no MAC-learning table)
- ❌ No SSH into the routers, no real shell

Everything in this roadmap is **additive** — it sits on top of the
platform without changing the 5-primitive data model.

---

## 1. IP & Address Management

The single biggest current UX gap. Today the user types every IP, every
mask, and every default route. Real networks automate this.

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 1.1 | ~~**Default gateway auto-suggest**~~ ✅ **shipped in M5-01** | 1 day | High | The peer's interface IP is already in the DB. Fill it in automatically. Entry point already accepts `DEFAULT_GATEWAY_IP` env var. Backend computes it in `node_service._default_gateway_for()`; entrypoint consumes it. Verified by `tests/manual/test_default_gateway_auto.py`. |
| 1.2 | ~~**DHCP server on the router**~~ ✅ **shipped in M5-01** | 3-4 days | **Massive** | The headline feature. `apk add dnsmasq` in `router-base.Dockerfile`. Add `POST /dhcp` + `GET /dhcp/leases` to the router agent. Add `dhcp_enabled` / `dhcp_pool_start` / `dhcp_pool_end` columns on `project_interfaces`. Run `udhcpc` at host boot. New router panel tab "DHCP". |
| 1.3 | ~~**DHCP relay / IP helper**~~ ✅ **shipped in M5-01** | 1-2 days | High | "One central DHCP server, many LANs." `dnsmasq --dhcp-relay=<server_ip>` per interface. `dhcp_relay_enabled` + `dhcp_relay_server_ip` columns on `project_interfaces`. `udhcpc -B` (broadcast flag) in the entrypoint — without it, dnsmasq's relayed OFFER is unicasted to an IP the client doesn't have yet and gets ARP-blackholed. |
| 1.4 | ~~**DHCP reservations**~~ ✅ **shipped in M5-01** | 1 day | High | Pair a host's MAC with a static IP the pool always hands out. New `project_dhcp_reservations` table with `(iface_id, mac_address)` + `(iface_id, ip_address)` unique constraints. `GET` / `PUT` / `DELETE` endpoints under each interface. `dhcp-host=MAC,IP[,hostname]` lines written into dnsmasq config. Ifaces get a deterministic locally-administered MAC at container attach time so reservations survive container restarts. Verified by `tests/manual/test_dhcp_reservations.py`. |
| 1.5 | **DHCPv6 + SLAAC** (IPv6 autoconfig) | 3-4 days | High | `radvd` for SLAAC; `dnsmasq` for stateful DHCPv6. Required once IPv6 ships. |
| 1.6 | **SLAAC only** (radvd) | 2-3 days | High | Simpler than DHCPv6; "IPv6 just works" for clients. |
| 1.7 | **IPv6 addressing on interfaces** | 1 week | High | `ip -6 addr add` in the router agent (the `ip` shell is already there). |
| 1.8 | **IPAM panel** — every used IP per project | 1 day | Medium | Show all IPs in use, with owner / subnet / status. |
| 1.9 | **Subnet calculator** in the IP-typing UI | 2-3 days | Medium | As the user types a mask, show network / broadcast / usable range. |
| 1.10 | ~~**Duplicate-IP detection**~~ ✅ **shipped in M5-01** | 1 day | High | Warn on save if two interfaces share an IP. Common student mistake. 409 `{error: "duplicate_ips", conflicts: [...]}` on `POST`/`PUT /projects/<pid>` and on `POST /projects/<pid>/start`. Sticky `DuplicateIPBanner` above the canvas polls `GET /projects/<pid>/duplicate-ips` and clears itself when the last conflict is fixed. Verified by `tests/manual/test_duplicate_ip_detection.py`. |
| 1.11 | **Auto-pick the next free IP** in a subnet | 1 day | High | "Add a host to this LAN, give it the next free IP." |

**Why first:** items 1.1, 1.2, 1.3 are the difference between "Packet
Tracer" and "a tool a real network engineer would use."

---

## 2. Security Features (the Cyber Range goal)

ContainerNet's stated end-state is "a foundation for a Virtual Cyber
Range." This section is where that goal becomes real.

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 2.1 | **ACLs on interfaces** (iptables / nftables) | 1 week | **Massive** | The #1 security primitive. New agent endpoints: `POST /acl`, `DELETE /acl`. New UI tab in the router panel. Per-interface in / out rules. |
| 2.2 | **Stateful firewall** (conntrack) | 1 week | **Massive** | Pair with 2.1. `nft add rule inet filter input ct state established,related accept`. |
| 2.3 | **Port scan attack mode** (nmap-style) | 3-4 days | High | Attacker container opens SYN to ports 1-1024 in sequence. New `anomaly`: "scan detected, X ports probed in Y seconds." |
| 2.4 | **Slowloris / HTTP slow attack** | 2-3 days | High | Open connections, send headers one byte at a time. |
| 2.5 | **DNS spoof attack** (responder-style) | 1 week | High | Attacker answers DNS queries with its own IP. New `anomaly` in the wire view. |
| 2.6 | **Credential brute-force attack** (SSH/HTTP) | 3-4 days | High | New `anomaly`: "auth failures > N per second." |
| 2.7 | **BGP hijack attack** (FRR `bgpd`) | 1 week | **Massive** | Announce a more-specific prefix via a rogue session. The crown-jewel Internet attack. |
| 2.8 | **VLAN hopping attack** (double-tagging) | 3-4 days | High | After VLANs ship. |
| 2.9 | **DHCP starvation attack** | 2-3 days | High | Attacker exhausts the DHCP pool. After 1.2 ships. |
| 2.10 | **MAC flooding attack** (CAM overflow) | 2-3 days | High | After a real switch ships. |
| 2.11 | **Rogue DHCP server attack** | 2-3 days | High | Attacker answers DHCP faster than the real one. Defence: DHCP snooping. |
| 2.12 | **ICMP redirect attack** | 2 days | Medium | Attacker sends fake ICMP redirects to redirect traffic through itself. |
| 2.13 | **IPv6 ND spoof** | 3 days | High | The IPv6 equivalent of ARP spoof. After IPv6 ships. |
| 2.14 | **DNS tunneling** (data exfiltration) | 1 week | High | Encode data in DNS queries to `evil.com`. |
| 2.15 | **TLS interception** (MITM proxy) | 2 weeks | High | `mitmproxy` in the attacker container. New `anomaly`: "TLS cert mismatch." |
| 2.16 | **WPA2-Enterprise attack** (Rogue AP) | 2 weeks | Medium | After Wi-Fi ships. |

**Defence pairings** (these should ship alongside the attacks):
- ARP spoof ↔ DAI + port security + DHCP snooping (2.x)
- DHCP starvation ↔ DHCP snooping rate limit
- MAC flood ↔ port security
- VLAN hop ↔ "set the native VLAN to one that's not in use"
- ICMP redirect ↔ `no ip redirects` (sysctl `net.ipv4.conf.all.accept_redirects=0`)

---

## 3. Routing (the heart of a router)

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 3.1 | **OSPF** (FRR) | 1-2 weeks | **Massive** | `apk add frr` in router-base. New `/ospf` endpoints. The "transition from static to dynamic" lesson. |
| 3.2 | **BGP** (FRR `bgpd`) | 1-2 weeks | **Massive** | The Internet's routing protocol. Pairs with 2.7 (BGP hijack). |
| 3.3 | **RIP** (FRR) | 3-4 days | Medium | Simple, taught first in many curricula. |
| 3.4 | **EIGRP** (FRR) | 1 week | Medium | Cisco-proprietary, common in enterprise. |
| 3.5 | **Static ↔ dynamic redistribution** | 3-4 days | High | "My static route gets advertised into OSPF." |
| 3.6 | **Route maps** (filter / set) | 1 week | High | "Advertise only 10.0.0.0/8, not 192.168/16." |
| 3.7 | **Policy-based routing** (multiple tables) | 3-4 days | Medium | `ip rule add from <src> table <name>`. |
| 3.8 | **ECMP** (equal-cost multi-path) | 3-4 days | Medium | "Two ISPs, both used." |
| 3.9 | **Recursive routing** | 2 days | Medium | Next-hop is itself a route. |
| 3.10 | **Floating static routes** (backup) | 2 days | Medium | Higher admin distance until the primary fails. |
| 3.11 | **Blackhole routes** (`ip route blackhole`) | 1 day | Medium | "Drop traffic to this prefix on purpose." |
| 3.12 | **Traceroute visualization on canvas** | 1 week | High | Animated path; each router lights up. Already partial (you have `MAX_HOPS=16`). |
| 3.13 | **Routing loop detection** | done | — | Partial in M4. Extend to highlight the loop in red. |
| 3.14 | **Convergence animation** (watch OSPF recompute) | 1 week | High | Pause a router, watch the SPF tree recompute in real time. |

---

## 4. High Availability & Redundancy

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 4.1 | **VRRP / HSRP** (`keepalived`) | 1 week | **Massive** | Two routers share a virtual IP. One dies, the other takes over in 1-3s. The "redundant default gateway" lab. |
| 4.2 | **CARP** (BSD-style) | 3 days | Medium | Also in `keepalived`. |
| 4.3 | **BFD** (Bidirectional Forwarding Detection) | 1 week | High | Sub-50ms link failure detection. |
| 4.4 | **Interface tracking** (route fails when interface down) | 3 days | Medium | `ip route replace <x> via <y> metric 10` + a tracker that flips the metric. |
| 4.5 | **Graceful restart** | 1 week | Medium | Router reboots, OSPF neighbors don't notice. |
| 4.6 | **Stack / multi-chassis** (two routers as one) | 2 weeks | Medium | Complex, but how real switches do it. |
| 4.7 | **First-hop reachability test** | 2-3 days | High | "How fast did failover actually happen?" — the user's "did it work?" test. |

---

## 5. NAT (Network Address Translation)

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 5.1 | **Source NAT / PAT** (many private → one public) | 2-3 days | **Massive** | `iptables -t nat -A POSTROUTING -s <lan> -o <wan> -j MASQUERADE`. The #1 NAT type. |
| 5.2 | **Destination NAT / port-forwarding** | 3 days | **Massive** | `iptables -t nat -A PREROUTING -d <pub> -p tcp --dport 80 -j DNAT --to-dest <priv>`. Exposes a server to the "Internet." |
| 5.3 | **Static NAT** (1:1 mapping) | 1 day | Medium | |
| 5.4 | **NAT64** (IPv6 → IPv4) | 1 week | High | After IPv6 ships. |
| 5.5 | **Carrier-grade NAT** (large-scale) | 1 week | Medium | |
| 5.6 | **NAT pool** (round-robin public IPs) | 3 days | Medium | |
| 5.7 | **NAT hairpinning** (internal client → own public IP) | 2 days | Medium | "Why can't I reach my own server from inside?" |
| 5.8 | **ALG** (Application-Level Gateway for FTP / SIP) | 1 week | Low | Niche. |
| 5.9 | **NAT anomaly detection** (translation table full) | 2-3 days | High | New anomaly signal. |

---

## 6. L2 Features on the Router (router-on-a-stick, etc.)

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 6.1 | **VLANs** (real, multi-bridge switch) | 2 weeks | **Massive** | The current switch is a transparent bridge. Real switch = one bridge per VLAN + a trunk between. |
| 6.2 | **802.1Q trunk** (router subinterfaces) | 1 week | **Massive** | `ip link add link eth0 name eth0.10 type vlan id 10`. The classic router-on-a-stick lab. |
| 6.3 | **VTP** (VLAN Trunking Protocol) | 1 week | Medium | |
| 6.4 | **STP / RSTP / MSTP** | 1-2 weeks | **Massive** | Required for any L2 loop. Use `mstpd` or `brctl` + `stp` toggles. |
| 6.5 | **EtherChannel / LACP** | 1 week | High | Two cables between two switches act as one. |
| 6.6 | **Port security** (MAC pinning) | 3-4 days | High | "Only this MAC is allowed on this port." Defence against MAC flood. |
| 6.7 | **DHCP snooping** | 3-4 days | High | "Drop DHCP offers from anyone but the trusted server." |
| 6.8 | **Dynamic ARP Inspection (DAI)** | 3-4 days | High | "Drop ARP from MACs that didn't get a DHCP lease." Defence against ARP spoof. |
| 6.9 | **Storm control** (broadcast suppression) | 2-3 days | Medium | |
| 6.10 | **Real switch with MAC-learning table** | 1-2 weeks | High | Currently a transparent bridge. Add a CAM table with aging. |
| 6.11 | **LLDP / CDP** (link-layer discovery) | 1 week | High | `show cdp neighbor`. The "I can see what's connected where" tool. |
| 6.12 | **BPDU guard / loop guard** | 3-4 days | Medium | |
| 6.13 | **Private VLAN** (promiscuous / isolated / community) | 1-2 weeks | Medium | |

---

## 7. Observability & Monitoring

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 7.1 | **Interface counters** + sparklines | 2-3 days | **Massive** | Read `/sys/class/net/<iface>/statistics/{rx,tx}_{packets,bytes}`. `show interfaces` is what every router has. |
| 7.2 | **Live traffic graphs per link** | 3-4 days | **Massive** | The most-asked feature: "show me bandwidth on this wire." |
| 7.3 | **SNMP** (`snmpd`) | 1 week | High | Every router has it. Standard tooling. |
| 7.4 | **NetFlow / sFlow / IPFIX** | 1-2 weeks | High | Flow export → collector. |
| 7.5 | **Centralized syslog server** | 1 week | High | "logging host" in router-speak. `rsyslog` or `syslog-ng`. |
| 7.6 | **NTP** (time sync) | 3 days | High | Logs need accurate time. `chronyd` in every node. |
| 7.7 | **Packet capture export** (download .pcap) | 2-3 days | High | "Open in Wireshark." |
| 7.8 | **Wireshark-compatible pcap stream** | 1 week | Medium | Real-time. |
| 7.9 | **Prometheus + Grafana** | 1 week | High | You already have `/metrics` on every agent. |
| 7.10 | **Per-port rate limit** (`tc tbf`) | 3-4 days | High | "Guest VLAN gets 10 Mbps." |
| 7.11 | **Latency / jitter / loss probes** | 1 week | High | SLA teaching. |
| 7.12 | **MTR** (continuous traceroute) | 3-4 days | Medium | |
| 7.13 | **Per-router `show tech-support`** | 3-4 days | High | One-click dump of every diagnostic command. |

---

## 8. Network Services (run them on routers / servers)

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 8.1 | **DNS server** (dnsmasq or BIND) | 1 week | **Massive** | Every network has DNS. |
| 8.2 | **Recursive DNS resolver with cache** | 1 week | High | |
| 8.3 | **NTP server** (`chrony` or `ntpd`) | 3 days | High | |
| 8.4 | **HTTP server** (`python -m http.server`) | done | — | Ship a real one (next item). |
| 8.5 | **Real web server** (nginx / Apache) | 3-4 days | High | |
| 8.6 | **SSH server** (dropbear) | 2-3 days | **Massive** | "I SSH into the router." |
| 8.7 | **Telnet server** (insecure, but taught) | 1 day | Medium | |
| 8.8 | **SMTP / IMAP server** | 1 week | Low | |
| 8.9 | **FTP / TFTP server** | 3-4 days | Medium | TFTP for router config backups. |
| 8.10 | **SNMP agent** (`snmpd`) | 1 week | High | |
| 8.11 | **RADIUS** (auth server) | 2 weeks | High | For 802.1X. |
| 8.12 | **Syslog server** | 1 week | High | |
| 8.13 | **TACACS+** (Cisco auth) | 1 week | Medium | |
| 8.14 | **HTTP forward proxy** (Squid) | 1 week | High | |
| 8.15 | **WireGuard VPN** (server + client) | 2 weeks | High | |
| 8.16 | **IPsec tunnel** (site-to-site) | 2 weeks | High | |
| 8.17 | **HAProxy load balancer** | 1 week | High | |
| 8.18 | **nginx as reverse proxy + TLS** | 1 week | High | |

---

## 9. Host OS / Server Features

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 9.1 | **Real Linux shell in the UI** (open a terminal on a host) | 1-2 weeks | **Massive** | WebSocket → container's `/bin/sh`. Transforms the project from "watcher" to "operator." |
| 9.2 | **VNC / noVNC** (graphical desktop) | 1-2 weeks | Medium | Overkill for most labs but fun. |
| 9.3 | **File transfer** (scp / rsync) | 1 week | High | |
| 9.4 | **Clickable tools** (`ping` / `traceroute` / `mtr` / `nslookup` / `dig`) | 1 week | High | Run from the host via the shell, show output in a side panel. |
| 9.5 | **Packet-crafting UI** (scapy-based) | 1-2 weeks | **Massive** | "I craft an ICMP redirect." GUI for scapy. |
| 9.6 | **Real applications** (curl, wget, netcat) | done | — | Already in the base image. |
| 9.7 | **Headless browser** in a host (HTTP testing) | 1-2 weeks | High | |
| 9.8 | **Database** (PostgreSQL, MySQL, Redis) inside a host | 3-4 days | Medium | |
| 9.9 | **Container-in-container** (Docker in a host) | 1 week | Low | Security nightmare. |

---

## 10. Authentication, Authorization, Accounting (AAA)

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 10.1 | **`enable` mode** on the router CLI | 1 week | **Massive** | Cisco's privileged EXEC. |
| 10.2 | **`configure terminal`** (config mode) | 1-2 weeks | **Massive** | The entire Cisco CLI paradigm. |
| 10.3 | **Local user database** (`username <u> privilege 15 secret <p>`) | 1 week | High | |
| 10.4 | **TACACS+ / RADIUS auth** for the router CLI | 1-2 weeks | High | |
| 10.5 | **Login banner** (`banner motd`) | 1 day | Low | |
| 10.6 | **Privilege levels** (1-15) | 1 week | High | |
| 10.7 | **Config persistence** (`copy running-config startup-config`) | 3-4 days | High | |
| 10.8 | **Config diff / rollback** | 1 week | High | |
| 10.9 | **Audit log of every command** | 1 week | High | For incident response. |
| 10.10 | **Login rate-limit** (`login block-for 60 attempts 3 within 30`) | 2-3 days | High | |

---

## 11. CLI / UX (Cisco-style command line)

The actual skill employers want from a network engineer.

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 11.1 | **Cisco-style CLI on the router** | 2-3 weeks | **Massive** | `show ip route`, `show ip interface brief`, `show ip arp`, etc. Backed by `ip` + the new ACL / NAT / OSPF code. |
| 11.2 | **Tab completion** | 1 week | High | |
| 11.3 | **`?` help** | 1 week | High | |
| 11.4 | **Command history** (↑/↓) | 1 week | High | |
| 11.5 | **`show running-config`** | 1 week | High | |
| 11.6 | **`show startup-config`** | 3 days | High | |
| 11.7 | **`show ip arp`** | done | — | Already in the panel. |
| 11.8 | **`show cdp neighbor`** | 1 week | High | After LLDP ships (6.11). |
| 11.9 | **`debug ip packet`** (live packet debug) | 1-2 weeks | High | |
| 11.10 | **`ping <ip>` from the CLI** | 1 week | High | |
| 11.11 | **`traceroute <ip>` from the CLI** | 1 week | High | |

---

## 12. WAN / Internet Simulation

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 12.1 | **ISP simulation** (a "cloud" node that drops 1% of packets) | 1 week | High | |
| 12.2 | **Latency simulation** (`tc netem delay 100ms`) | 2-3 days | **Massive** | "My VoIP is bad." |
| 12.3 | **Packet loss simulation** (`tc netem loss 1%`) | 2-3 days | High | |
| 12.4 | **Jitter simulation** (`tc netem jitter 20ms`) | 2-3 days | High | |
| 12.5 | **Bandwidth shaping** (`tc tbf rate 10mbit`) | 3-4 days | High | |
| 12.6 | **Reorder / duplicate / corrupt packets** | 2-3 days | Medium | |
| 12.7 | **Geo-distributed "Internet"** | 1-2 weeks | Medium | Multiple compose projects with simulated WAN. |
| 12.8 | **BGP looking glass** (real-world BGP routes into the lab) | 2 weeks | High | Pull data from `routeviews.org`. |

---

## 13. Multi-Project & Multi-User

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 13.1 | **Project sharing** (read-only URL) | 1 week | High | Instructor demos. |
| 13.2 | **Multi-user collaboration** (live cursors) | 2-3 weeks | High | Team labs. |
| 13.3 | **User accounts** (vs single-user dev mode) | 1-2 weeks | High | |
| 13.4 | **Permissions per project** (owner / editor / viewer) | 1 week | High | |
| 13.5 | **Project templates** (still blank by default, but save your own) | 1 week | Medium | |
| 13.6 | **Project export / import** (YAML topology file) | 3-4 days | High | Share setups. |
| 13.7 | **Git-like versioning** (project history) | 2 weeks | Medium | |
| 13.8 | **Multi-tenant** (many isolated backends) | 2 weeks | Low | Academic only. |
| 13.9 | **Class roster** | 1-2 weeks | High | Instructor view. |
| 13.10 | **Per-student sandbox** | 1-2 weeks | High | Auto-provision a fresh project per student. |

---

## 14. Teaching / Pedagogical Features

This is what turns ContainerNet from a tool into a curriculum.

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 14.1 | **Step-by-step lab mode** | 1-2 weeks | **Massive** | "Complete step 1: configure Host-1's IP." Guided labs. |
| 14.2 | **Auto-grader** | 2 weeks | **Massive** | "Did the student achieve the goal?" Homework auto-check. |
| 14.3 | **Quiz mode** (multiple-choice inside the UI) | 1 week | High | |
| 14.4 | **Hint system** (progressive) | 1 week | High | |
| 14.5 | **Time tracker** (how long did this take?) | 2-3 days | Medium | |
| 14.6 | **Achievement / badge system** | 1 week | Medium | Gamification. |
| 14.7 | **Pre-built scenarios** | 1 week each | High | The killer demo is one; build 20 more (see §15). |
| 14.8 | **Score / leaderboard** | 1 week | Low | |
| 14.9 | **Replay** (record and replay a session) | 2 weeks | High | |
| 14.10 | **Annotations** (instructor writes notes on the canvas) | 1 week | High | |
| 14.11 | **Recording** (every event timestamped, exportable) | 2 weeks | High | |

---

## 15. Test / Lab Scenarios (pre-canned labs)

Each one is a small project + a teaching card. Most take ~1 week each to
design, less to add once the underlying features exist.

- "Configure OSPF on a 3-router topology" (needs 3.1)
- "Stop an ARP spoof with DAI" (needs 2.x + 6.8)
- "Find the rogue DHCP server" (needs 1.2 + 2.11)
- "Trace a BGP hijack" (needs 3.2 + 2.7)
- "Configure VRRP, kill one router, watch the other take over" (needs 4.1)
- "Configure NAT, prove a host can reach 'the Internet'" (needs 5.1)
- "ACL that blocks ICMP, prove it with ping" (needs 2.1)
- "VLAN: separate two departments on one switch" (needs 6.1)
- "BFD detects a link failure in <50ms" (needs 4.3)
- "QoS: give VoIP priority over web" (needs 7.10)
- "Redundant LACP link between two switches" (needs 6.5)
- "DHCP relay across subnets" (needs 1.3)
- "DNS: configure split-horizon DNS" (needs 8.1)
- "SSH into a router using TACACS+ auth" (needs 8.6 + 10.4)
- "Packet crafting: forge an ICMP redirect" (needs 9.5)
- "VLAN hopping: tag a packet to escape your VLAN" (needs 6.1 + 2.8)
- "DHCP starvation: exhaust the pool" (needs 1.2 + 2.9)
- "BGP route filtering: reject your peer's hijack" (needs 3.2 + 3.6)
- "OSPF area design: keep the LSDB small" (needs 3.1)
- "ECMP: two ISPs, both used" (needs 3.8)
- "TFTP: back up your router's config" (needs 8.9 + 10.7)

---

## 16. Developer / Operator Features

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 16.1 | **Hot-reload of Python agents** | 3-4 days | High | Edit the agent without restarting the project. |
| 16.2 | **Per-project resource limits** (CPU / RAM) | 2-3 days | Operational | |
| 16.3 | **Project quota** (max N per backend) | 1 day | Operational | |
| 16.4 | **Backend health dashboard** | 1 week | Operational | |
| 16.5 | **Topology diff** (compare two projects) | 1 week | High | "What did the student change?" |
| 16.6 | **CLI for the backend** (`containernet start <project>`) | 1 week | Operational | |
| 16.7 | **Webhook for project state changes** | 2-3 days | Operational | |
| 16.8 | **GraphQL API** | 1-2 weeks | Low | Overkill. |
| 16.9 | **gRPC API** | 1-2 weeks | Low | |
| 16.10 | **OpenAPI spec** | done | — | FastAPI does this automatically. |
| 16.11 | **CI/CD for ContainerNet itself** | 1 week | Operational | |
| 16.12 | **End-to-end test suite** in CI | 1-2 weeks | Operational | You have 2 manual tests. |

---

## 17. UI / UX Improvements

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 17.1 | **Drag-to-resize nodes** | 2-3 days | High | Show name + IP inline. |
| 17.2 | **Mini-map of the topology** | 1 day | High | React Flow has it built-in. |
| 17.3 | **Search bar** for nodes / IPs / MACs | 2-3 days | High | |
| 17.4 | **Dark / light theme toggle** | 3-4 days | Low | By design, dark only. |
| 17.5 | **Mobile / tablet view** | 2 weeks | Low | |
| 17.6 | **Accessibility (WCAG)** | 1-2 weeks | Low | |
| 17.7 | **Internationalization** | 1-2 weeks | Low | |
| 17.8 | **Topology export as image** (PNG / SVG) | 2-3 days | High | For reports. |
| 17.9 | **Topology export as LaTeX / TikZ** | 1 week | High | For assignments. |
| 17.10 | **Topology export as JSON** | 2-3 days | High | For tooling. |
| 17.11 | **Undo / redo across more actions** | 1 week | High | Already in the canvas; extend to attacks / routes. |
| 17.12 | **Live cursors / presence** | 2-3 weeks | Medium | |
| 17.13 | **Comments on nodes** (instructor feedback) | 1 week | High | |
| 17.14 | **Per-node health badge** (up / down / degraded) | 2-3 days | High | |
| 17.15 | **Animated packet flow** (a glowing dot moving along a wire) | 1-2 weeks | **Massive** | "Watch the packet travel." |
| 17.16 | **Replay / scrub timeline** | 2 weeks | High | |
| 17.17 | **Subnet overlay** (color nodes by subnet) | 3-4 days | High | Already have `subnet-1` through `subnet-6`. |
| 17.18 | **Topology thumbnails** on the projects page | 2-3 days | High | "Visual project list." |
| 17.19 | **Keyboard shortcut for everything** | 1 week | High | You have `?` already. Extend. |

---

## 18. Real Switch & Hardware Simulation

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 18.1 | **Real MAC-learning table** (CAM with aging) | 1-2 weeks | High | Currently a transparent bridge. |
| 18.2 | **Trunk port** (multiple VLANs) | 1-2 weeks | High | |
| 18.3 | **Access port** (single VLAN, untagged) | 1 week | High | |
| 18.4 | **Voice VLAN** | 1 week | Medium | Auto-assign IP phone to VLAN. |
| 18.5 | **Layer-3 switch** (SVI) | 1-2 weeks | High | A switch that routes. |
| 18.6 | **Hardware simulation** (port speeds) | 1-2 weeks | Medium | 100M / 1G / 10G with realistic throughput limits. |
| 18.7 | **Cable delay** (light-speed in long fiber) | 1 week | Medium | `tc netem delay`. |
| 18.8 | **Console port** (RJ-45 / USB serial) | 1-2 weeks | Low | Niche. |
| 18.9 | **Switch ASIC simulation** (cut-through vs store-and-forward) | 2 weeks | Low | Deep, niche. |

---

## 19. Wireless / Wi-Fi

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 19.1 | **Wi-Fi AP node** (`hostapd`) | 2-3 weeks | High | |
| 19.2 | **Wi-Fi client node** (`wpa_supplicant`) | 1-2 weeks | High | |
| 19.3 | **WPA2-PSK** | 1 week | High | |
| 19.4 | **WPA2-Enterprise** (802.1X + RADIUS) | 2 weeks | High | |
| 19.5 | **WPA3** | 2 weeks | High | |
| 19.6 | **Rogue AP detection** | 1 week | High | |
| 19.7 | **Evil twin attack** | 1 week | High | |
| 19.8 | **Deauth attack** | 1 week | High | |
| 19.9 | **WIDS / WIPS** | 2-3 weeks | High | |
| 19.10 | **Wi-Fi packet capture** (monitor mode) | 1-2 weeks | High | |

---

## 20. Service Mesh / Overlay

| # | Feature | Effort | Value | Notes |
|---|---|---|---|---|
| 20.1 | **GRE tunnel** | 1 week | Medium | |
| 20.2 | **IPIP tunnel** | 1 week | Medium | |
| 20.3 | **VXLAN** | 1-2 weeks | High | Modern data center. |
| 20.4 | **MPLS** | 2-3 weeks | High | Service provider networks. |
| 20.5 | **Segment Routing** | 2-3 weeks | High | |
| 20.6 | **Service mesh** (Istio / Linkerd) | 2-4 weeks | Medium | |

---

## ⭐ Top-10 Picks (if you can only do 10)

These are the highest value-per-day features for a Virtual Cyber Range.
Total: **~3-4 months of focused work** to go from "Packet Tracer" to
"real enterprise network lab."

| # | Feature | Effort | Why |
|---|---|---|---|
| 1 | **DHCP server on the router** | 3-4 days | Solves the static-IP problem; one of the top 3 features to add. |
| 2 | **NAT (source NAT / PAT)** | 2-3 days | The other half of "real Internet" — without NAT, private IPs go nowhere. |
| 3 | **ACLs on interfaces** | 1 week | Enables a whole class of attacks + defences. The #1 security primitive. |
| 4 | **OSPF via FRR** | 1-2 weeks | The transition from "I type every route" to "the network learns." |
| 5 | **VRRP / HSRP** | 1 week | Redundant default gateway — the first "high availability" lesson. |
| 6 | **Interface counters + traffic graphs** | 2-3 days | Free win from `/sys/class/net`; users love it. |
| 7 | **SSH into routers** (real shell) | 1-2 weeks | Transforms the project from "watcher" to "operator." |
| 8 | **Cisco-style CLI on routers** | 2-3 weeks | The actual skill employers want. |
| 9 | **VLANs (real, with subinterfaces + trunks)** | 2 weeks | Required for "real" enterprise labs. |
| 10 | **BGP + BGP hijack attack** | 2 weeks | The crown jewel of the Cyber Range goal. |

---

## Suggested Quarter Plan

If you want a 12-month plan:

**Q1 — Make it usable**
- ~~1.1 Default gateway auto-suggest~~ ✅
- ~~1.2 DHCP server on the router~~ ✅
- ~~1.3 DHCP relay~~ ✅
- ~~1.4 DHCP reservations~~ ✅
- ~~1.10 Duplicate-IP detection~~ ✅
- 5.1 Source NAT / PAT
- 5.2 Destination NAT
- 7.1 Interface counters + sparklines
- 7.2 Live traffic graphs per link
- 9.1 Real Linux shell in the UI
- 9.4 Clickable tools (ping / traceroute / mtr / nslookup)

**Q2 — Make it real (L2 + L3)**
- 3.1 OSPF
- 3.2 BGP
- 4.1 VRRP / HSRP
- 4.3 BFD
- 6.1 VLANs
- 6.2 802.1Q trunk
- 6.4 STP / RSTP
- 6.5 EtherChannel / LACP
- 6.11 LLDP / CDP

**Q3 — Make it teachable (security + AAA + CLI)**
- 2.1 ACLs on interfaces
- 2.3 Port scan attack
- 2.7 BGP hijack attack
- 2.15 TLS interception
- 8.6 SSH server (dropbear)
- 8.10 SNMP agent
- 10.1-10.9 AAA (full Cisco-style CLI)
- 11.1-11.11 Cisco-style CLI

**Q4 — Make it a platform (teaching + multi-user + polish)**
- 13.1 Project sharing
- 13.3 User accounts
- 13.6 Project export / import
- 14.1 Step-by-step lab mode
- 14.2 Auto-grader
- 15.x Pre-built scenarios (5-10 of them)
- 17.15 Animated packet flow
- 17.16 Replay / scrub timeline

**Total: ~52 features, ~80-100 working days, $0 in licenses.**

---

## Architecture note

Everything in this roadmap is **additive**. It sits on top of the
M4 platform without changing the 5-primitive data model.

Every feature is one of:

- A new Alpine `apk add` (dnsmasq, frr, keepalived, nftables, sshd,
  snmpd, hostapd, isc-dhcp-server, …)
- A new HTTP endpoint on the router agent
- A new tab in the router panel
- A new column on `project_interfaces` or `project_nodes`
- A new event kind on the WebSocket
- A new anomaly signal in `anomaly_detector.py`

You don't need to re-architect anything. You just need to pick the
next 1-3 features and ship them.

---

## Related docs

- [`README.md`](./README.md) — the project overview.
- [`M4_OVERVIEW.md`](./M4_OVERVIEW.md) — the detailed walk-through of
  every shipped M4 phase.
- [`architecture.md`](./architecture.md) — the system-level
  architecture.
- [`RUNBOOK.md`](./RUNBOOK.md) — the on-call contributor runbook.
- [`phases/milestone-4/`](./phases/milestone-4/) — the per-phase
  plans and acceptance docs.
