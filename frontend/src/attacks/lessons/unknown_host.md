## Unknown Host

The attacker just *sits on the link* and occasionally emits a ping to the
target. No packets look malicious in isolation — but the new MAC is
suddenly there.

### Why this mode matters

In a real lab this is the "reconnaissance" baseline. If you can spot a
**new** host on your wire that *shouldn't* be there, you've found an
intruder before they did anything obviously bad. The earlier you spot
them, the better.

### What gets logged

- The router's `ip neigh` table shows a new entry
- The router's anomaly detector fires `new_mac` the first time it sees
  a MAC it doesn't recognise
- All other hosts on the link see the new source MAC in their `ip neigh`

### How ContainerNet detects it

The router polls `ip neigh show dev <iface>` every 2 s. Any MAC not in
the snapshot from the previous poll fires a `new_mac` anomaly event
with `severity=warn`.

### How to defend

- **802.1X** port-based authentication — only authorised MACs allowed
- **Switch port security** — auto-shut port on unknown MAC
- **Network Access Control (NAC)** — Cisco ISE, Aruba ClearPass
- **Active monitoring** — compare live `ip neigh` against an inventory

### Real-world analogues

- An attacker plugging a laptop into an empty cubicle port
- A rogue Wi-Fi access point
- The "unauthenticated device on the network" finding from any pen-test