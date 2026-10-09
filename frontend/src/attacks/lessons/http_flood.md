## HTTP Flood (L7 DoS)

Instead of dial-up raw Sockets, the attacker opens 500 aiohttp POSTs per
second to the victim's `/communications` endpoint.

### What happens on the wire

A burst of fully-formed HTTP requests — they're hard to filter because
each one passes the TCP handshake. The victim spends CPU + DB time on
each request; the service degrades long before the SYN queue fills.

### Why L7 is more dangerous than L3/L4

- Each request burns **CPU, RAM, and DB time**, not just kernel state
- Looks like legitimate traffic at the network layer
- Hard to rate-limit without dropping real users

### How ContainerNet detects it

The attacker's `/state` reports ~500 req/s. Backend thresholds: anything
> 20 req/s for >5 s fires `http_rate`.

### How to defend

- **CDN / WAF** (Cloudflare, AWS Shield) absorbs the volume before it
  reaches your origin
- **Per-IP rate limits** + **JS challenges** for bots
- **Cache** static + cacheable dynamic responses
- **Load-shedding** queue (return 503 fast when saturated)

### Real-world analogues

- `slowloris`, `GoldenEye`, `HOIC`
- Mirai-style HTTP GET/POST floods
- Application-layer DDoS (Layer 7)