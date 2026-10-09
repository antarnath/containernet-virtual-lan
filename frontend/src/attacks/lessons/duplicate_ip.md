## Duplicate IP

The attacker adds the victim's IP as a secondary address on their own
interface (`ip addr add <victim>/32 dev eth0`). Suddenly two machines
on the link claim the same IP.

### What happens on the wire

- ARP for `D` may be answered by either host, depending on timing +
  kernel `arp_ignore` settings
- TCP SYN to `D` races between the two — whichever arrives first wins
- The victim's outbound traffic continues to flow, but inbound traffic
  for `D` may now land on the attacker
- Many kernels start logging "martian packet" warnings

### How ContainerNet detects it

The backend's attack_detector maps `duplicate_ip` mode → `duplicate_ip`
signal kind. Any time the attacker reports `running=true` in
`duplicate_ip`, a `duplicate_ip` row is written. The router's anomaly
detector also notices when a neighbour IP suddenly maps to two MACs.

### How to defend

- **DHCP snooping** + **DAI (Dynamic ARP Inspection)** to reject packets
  whose source IP is not the one the switch saw at DHCP time
- **IP source guard** on access ports
- **Sticky ARP** entries on critical servers

### Real-world analogues

- The classic "land" attack cousin
- VM escape scenarios where a guest hijacks the host's IP
- `arping -A` (ARP announcement) storm