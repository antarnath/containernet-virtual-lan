## ARP Spoofing

The attacker sends a forged ARP reply (a "gratuitous ARP") onto the local
link every second, claiming:

> "Hey everyone — IP `<target>` is at MY MAC address."

### What happens on the wire

Every other host on the link overwrites their ARP entry for `<target>` and
starts forwarding frames intended for `<target>` to the attacker. The
attacker can then:

- **Read** the victim's traffic (passive sniffing)
- **Modify** it before relaying it on (a "man-in-the-middle")
- **Drop** it (a black-hole denial of service)

### How ContainerNet detects it

The router polls `ip neigh` every 2 s and compares the live MAC against
the one it learned at boot. A change fires an `arp_mac_change` anomaly
event and re-colors the wire-view port badge.

### How to defend

- **Static ARP entries** on critical hosts (`arp -s <ip> <mac>`)
- **Dynamic ARP Inspection** on managed switches
- **Port security** + **DHCP snooping** to lock down MAC ↔ IP ↔ port

### Real-world analogues

- `ettercap`, `arpspoof`, `mitmproxy` ARP mode
- The "router poisoning" half of an active MITM