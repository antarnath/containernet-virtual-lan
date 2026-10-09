## TCP SYN Flood

A classic denial-of-service: the attacker opens 50 fresh TCP connections
per second to the victim's `:8080` and never completes the 3-way handshake.

### What happens on the wire

For every connection the attacker sends a `SYN`, the victim replies
`SYN-ACK` and reserves kernel state for the half-open socket. The
attacker never sends the final `ACK`. The victim accumulates half-open
connections until:

- The kernel's SYN backlog fills → new SYNs are silently dropped
- The listener's `accept()` queue fills → the service stops accepting
- Memory pressure slows the box → everything is degraded

### How ContainerNet detects it

The attacker's `/state` reports a SYN rate of ~50/s. The backend's
`attack_detector` polls every second; a rate > 5/s for the same attacker
fires an `syn_rate` signal.

### How to defend

- **SYN cookies** — kernel replies with a stateless SYN-ACK whose seq
  number encodes the connection state, so no half-open socket is needed
- **Rate-limiting** new connections per source IP
- **CDN / WAF** in front of the service
- **Lower conn on**: SYN burst detection at the firewall

### Real-world analogues

- `hping3 --flood` (regular SUSE-distributed hping3, ~130 kpps/core)
- The original 1996 "ping of death"-era SYN floods
- Mirai botnet TCP SYN scans