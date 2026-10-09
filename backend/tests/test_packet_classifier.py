"""Unit test for the protocol classifier (M4 phase 04).

Run inside the backend container with::

    python tests/test_packet_classifier.py

Exercises the classifier against hand-built NDJSON samples that
mirror the real capture shim's output. The classifier must
correctly map the shim's `l2.ethertype_name` and `l3.protocol_name`
+ L7 fields to the design system's small set
(tcp / udp / icmp / arp / http / other).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.services.packet_service import (
    PROTO_ARP,
    PROTO_HTTP,
    PROTO_ICMP,
    PROTO_OTHER,
    PROTO_TCP,
    PROTO_UDP,
    VALID_PROTOCOLS,
    classify_protocol,
)


# Hand-built packets modeled on capture_shim.py's output. We use
# only the fields the classifier reads.

PKT_TCP = {
    "l2": {"ethertype_name": "IPv4", "src_mac": "02:42:0a:00:00:01"},
    "l3": {
        "protocol_name": "TCP",
        "src_ip": "10.0.0.1",
        "dst_ip": "10.0.0.2",
    },
    "l4": {"src_port": 52412, "dst_port": 80},
    "l7": None,
}

PKT_HTTP_REQUEST = {
    "l2": {"ethertype_name": "IPv4"},
    "l3": {"protocol_name": "TCP"},
    "l4": {"src_port": 52412, "dst_port": 8080},
    "l7": {"is_request": True, "method": "GET", "path": "/"},
}

PKT_HTTP_RESPONSE = {
    "l2": {"ethertype_name": "IPv4"},
    "l3": {"protocol_name": "TCP"},
    "l4": {"src_port": 80, "dst_port": 52412},
    "l7": {"is_response": True, "status_code": 200},
}

PKT_UDP = {
    "l2": {"ethertype_name": "IPv4"},
    "l3": {"protocol_name": "UDP"},
    "l4": {"src_port": 53, "dst_port": 33333},
    "l7": None,
}

PKT_ICMP = {
    "l2": {"ethertype_name": "IPv4"},
    "l3": {"protocol_name": "ICMP"},
    "l4": {},
    "l7": None,
}

PKT_ARP = {
    "l2": {"ethertype_name": "ARP"},
    "l3": None,
    "l4": None,
    "l7": None,
}

PKT_UNKNOWN = {
    "l2": {"ethertype_name": "IPv6"},
    "l3": {"protocol_name": "SCTP"},
    "l4": {},
    "l7": None,
}

PKT_BROKEN = {"l2": {"_error": "short"}}


def main() -> None:
    cases = [
        (PKT_TCP, PROTO_TCP),
        (PKT_HTTP_REQUEST, PROTO_HTTP),
        (PKT_HTTP_RESPONSE, PROTO_HTTP),
        (PKT_UDP, PROTO_UDP),
        (PKT_ICMP, PROTO_ICMP),
        (PKT_ARP, PROTO_ARP),
        (PKT_UNKNOWN, PROTO_OTHER),
        (PKT_BROKEN, PROTO_OTHER),
        (None, PROTO_OTHER),
        ({}, PROTO_OTHER),
    ]
    for pkt, expected in cases:
        got = classify_protocol(pkt)
        assert got in VALID_PROTOCOLS, f"classifier returned unknown {got!r}"
        assert got == expected, f"for {pkt!r}: expected {expected!r}, got {got!r}"
    print("OK: %d classifier cases pass" % len(cases))


if __name__ == "__main__":
    main()
