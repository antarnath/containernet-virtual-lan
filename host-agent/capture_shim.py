#!/usr/bin/env python3
"""
Capture shim for the ContainerNet dashboard.

Reads binary pcap from stdin (as written by `tcpdump -w -`),
parses each packet into the structured form described in
phase_m2-07 §3 (NDJSON, one PacketEvent per line on stdout),
recomputes IP and TCP checksums per RFC 1071, and emits
`checksum_ok: true|false` for each layer.

Stdlib only — no third-party deps, so this runs in the slim
capture-base image.

Usage:
    tcpdump -i any -U -l -tttt -nn -vvv -w - | python3 capture_shim.py

Or against a captured pcap file:
    python3 capture_shim.py < sample.pcap
"""
from __future__ import annotations

import json
import struct
import sys
from typing import Any, Optional


# ─── pcap globals (little-endian file header) ────────────────────
PCAP_MAGIC_LE = 0xA1B2C3D4
PCAP_MAGIC_BE = 0xD4C3B2A1

# Linktype values we care about.
LINKTYPE_ETHERNET = 1
LINKTYPE_LINUX_SLL = 113   # Linux cooked v1 (legacy)
LINKTYPE_LINUX_SLL2 = 276  # Linux cooked v2 — what tcpdump emits on
                           # `-i any` inside a containerized env.


# ─── Ethernet ─────────────────────────────────────────────────────
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_ARP = 0x0806
ETHERTYPE_IPV6 = 0x86DD


def mac_bytes_to_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def parse_l2(linktype: int, frame: bytes) -> tuple[dict, bytes]:
    """Return (L2Frame-dict, layer-3-payload-bytes).

    Handles three linktypes:
      * 1   — standard Ethernet II
      * 113 — Linux cooked v1 (SLL), 16-byte header
      * 276 — Linux cooked v2 (SLL2), 20-byte header
    """
    if linktype == LINKTYPE_ETHERNET:
        if len(frame) < 14:
            return ({"_error": "frame too short", "len": len(frame)}, b"")
        dst = frame[0:6]
        src = frame[6:12]
        ethertype = struct.unpack("!H", frame[12:14])[0]
        payload = frame[14:]
        is_broadcast = dst == b"\xff\xff\xff\xff\xff\xff"
        return (
            {
                "src_mac": mac_bytes_to_str(src),
                "dst_mac": mac_bytes_to_str(dst),
                "ethertype": ethertype,
                "ethertype_name": _ethertype_name(ethertype),
                "is_broadcast": is_broadcast,
                "linktype": linktype,
            },
            payload,
        )

    if linktype == LINKTYPE_LINUX_SLL2:
        # Linux Cooked v2 (20-byte header):
        #   0-1  protocol family (uint16 BE) — same values as EtherType
        #   2-3  reserved
        #   4    address length
        #   5-12 sender address (8 bytes; padded to 8)
        #   13   padding
        #   14-19 unused
        if len(frame) < 20:
            return ({"_error": "sll2 frame too short", "len": len(frame)}, b"")
        ethertype = struct.unpack("!H", frame[0:2])[0]
        sender_bytes = frame[5:11]
        # L2 destination in SLL2 isn't actually transmitted (SLL2 captures
        # post-decision); use a synthetic "any" destination.
        dst = b"\x00\x00\x00\x00\x00\x00"
        payload = frame[20:]
        return (
            {
                "src_mac": mac_bytes_to_str(sender_bytes),
                "dst_mac": mac_bytes_to_str(dst),
                "ethertype": ethertype,
                "ethertype_name": _ethertype_name(ethertype),
                "is_broadcast": ethertype == ETHERTYPE_ARP,
                "linktype": linktype,
            },
            payload,
        )

    if linktype == LINKTYPE_LINUX_SLL:
        # Linux Cooked v1 (16-byte header) — legacy.
        if len(frame) < 16:
            return ({"_error": "sll frame too short", "len": len(frame)}, b"")
        ethertype = struct.unpack("!H", frame[0:2])[0]
        sender_bytes = frame[6:12]
        dst = b"\x00\x00\x00\x00\x00\x00"
        payload = frame[16:]
        return (
            {
                "src_mac": mac_bytes_to_str(sender_bytes),
                "dst_mac": mac_bytes_to_str(dst),
                "ethertype": ethertype,
                "ethertype_name": _ethertype_name(ethertype),
                "is_broadcast": ethertype == ETHERTYPE_ARP,
                "linktype": linktype,
            },
            payload,
        )

    return (
        {
            "_error": f"unsupported linktype {linktype}",
            "linktype": linktype,
        },
        b"",
    )


def _ethertype_name(ethertype: int) -> str:
    return {
        ETHERTYPE_IPV4: "IPv4",
        ETHERTYPE_ARP: "ARP",
        ETHERTYPE_IPV6: "IPv6",
    }.get(ethertype, f"0x{ethertype:04x}")


# ─── IPv4 ─────────────────────────────────────────────────────────
PROTO_ICMP = 1
PROTO_TCP = 6
PROTO_UDP = 17


def ipv4_to_str(b: bytes) -> str:
    return ".".join(str(x) for x in b)


def internet_checksum(data: bytes) -> int:
    """RFC 1071 ones-complement checksum over `data`."""
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def raw_sum(data: bytes) -> int:
    """Sum the 16-bit words of `data` as an unsigned integer, no
    complement. Useful for TX-checksum-offload detection: the kernel
    writes the raw (unfolded) sum of the pseudo-header into the TCP
    checksum field and lets the NIC hardware add the rest of the
    segment."""
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return s & 0xFFFF


def parse_ipv4(packet: bytes) -> tuple[dict, bytes]:
    """Return (L3IPv4-dict, payload-bytes)."""
    if len(packet) < 20:
        return ({"_error": "ip packet too short", "len": len(packet)}, b"")
    v_ihl = packet[0]
    version = v_ihl >> 4
    ihl = (v_ihl & 0x0F) * 4
    dscp_ecn = packet[1]
    dscp = dscp_ecn >> 2
    ecn = dscp_ecn & 0x03
    total_length = struct.unpack("!H", packet[2:4])[0]
    identification = struct.unpack("!H", packet[4:6])[0]
    flags_frag = struct.unpack("!H", packet[6:8])[0]
    flags = (flags_frag >> 13) & 0x07
    fragment_offset = flags_frag & 0x1FFF
    ttl = packet[8]
    proto = packet[9]
    checksum_in_packet = struct.unpack("!H", packet[10:12])[0]
    src_ip = packet[12:16]
    dst_ip = packet[16:20]
    payload = packet[ihl:total_length]

    # Recompute header checksum (with checksum field zeroed).
    header_for_cksum = packet[:ihl]
    cksum_computed = internet_checksum(
        header_for_cksum[:10] + b"\x00\x00" + header_for_cksum[12:ihl]
    )
    checksum_ok = cksum_computed == checksum_in_packet

    flag_str = ""
    if flags & 0x2:
        flag_str += "DF"
    if flags & 0x4:
        flag_str += "MF"

    return (
        {
            "version": version,
            "ihl": ihl // 4,
            "dscp": dscp,
            "ecn": ecn,
            "total_length": total_length,
            "identification": f"0x{identification:04x}",
            "flags": flag_str or "none",
            "fragment_offset": fragment_offset,
            "ttl": ttl,
            "protocol": proto,
            "protocol_name": {
                PROTO_ICMP: "ICMP",
                PROTO_TCP: "TCP",
                PROTO_UDP: "UDP",
            }.get(proto, str(proto)),
            "checksum": f"0x{checksum_in_packet:04x}",
            "checksum_ok": checksum_ok,
            "src_ip": ipv4_to_str(src_ip),
            "dst_ip": ipv4_to_str(dst_ip),
        },
        payload,
    )


# ─── TCP ──────────────────────────────────────────────────────────
# Standard TCP flag bits in the 8-bit flags byte (RFC 9293 §3.1).
# The 9-bit "flags" field of a TCP header (offset 12-13) packs
# data_offset (high 4 bits of byte 12), reserved (next 3 bits),
# NS (low bit of byte 12) plus the 8 flag bits of byte 13.
# We pass the low 8 bits of the !H at offset 12 here.
TCP_FLAG_NAMES = [
    (0x80, "CWR"),
    (0x40, "ECE"),
    (0x20, "URG"),
    (0x08, "PSH"),
    (0x04, "RST"),
    (0x02, "SYN"),
    (0x01, "FIN"),
    (0x10, "ACK"),  # ACK last so "SYN,ACK" sorts before final ACK
]


def tcp_flags_to_list(flags_byte: int) -> list[str]:
    return [name for bit, name in TCP_FLAG_NAMES if flags_byte & bit]


def parse_tcp(segment: bytes, src_ip: bytes, dst_ip: bytes) -> tuple[dict, bytes]:
    """Return (L4TCP-dict, payload-bytes)."""
    if len(segment) < 20:
        return ({"_error": "tcp segment too short", "len": len(segment)}, b"")
    src_port = struct.unpack("!H", segment[0:2])[0]
    dst_port = struct.unpack("!H", segment[2:4])[0]
    seq = struct.unpack("!I", segment[4:8])[0]
    ack = struct.unpack("!I", segment[8:12])[0]
    data_off_flags = struct.unpack("!H", segment[12:14])[0]
    data_offset = (data_off_flags >> 12) * 4
    # RFC 9293: top 4 bits of byte 12 = data offset; next 3 bits reserved;
    # low bit of byte 12 = NS; byte 13 = CWR ECE URG ACK PSH RST SYN FIN.
    flags_bits = data_off_flags & 0x00FF
    window = struct.unpack("!H", segment[14:16])[0]
    checksum_in_segment = struct.unpack("!H", segment[16:18])[0]
    urgent = struct.unpack("!H", segment[18:20])[0]
    payload = segment[data_offset:]
    options = segment[20:data_offset]

    # TCP checksum with pseudo-header.
    tcp_len = len(segment)
    pseudo = src_ip + dst_ip + b"\x00" + bytes([PROTO_TCP]) + struct.pack("!H", tcp_len)
    cksum_computed = internet_checksum(pseudo + segment[:16] + b"\x00\x00" + segment[18:])
    # Linux TX-checksum-offload optimization: the kernel writes the
    # raw 16-bit sum of the pseudo-header into the TCP checksum field
    # and lets the NIC hardware complete the sum by adding the rest of
    # the segment (TCP header bytes 18-end + payload). When tcpdump
    # captures the frame BEFORE the NIC has touched it, the captured
    # checksum field equals raw_sum(pseudo_only) and is NOT a valid
    # full checksum. We detect this case so the dashboard can label
    # the packet "offloaded" instead of incorrectly "invalid".
    pseudo_only_sum = raw_sum(pseudo)
    checksum_offloaded = (pseudo_only_sum == checksum_in_segment)
    checksum_ok = cksum_computed == checksum_in_segment or checksum_offloaded

    # Decode common options (best-effort, not all).
    decoded_opts: list[dict] = []
    i = 0
    while i < len(options):
        kind = options[i]
        if kind == 0:  # End
            decoded_opts.append({"kind": "EOL"})
            break
        if kind == 1:  # NOP
            decoded_opts.append({"kind": "NOP"})
            i += 1
            continue
        if i + 1 >= len(options):
            break
        length = options[i + 1]
        if length < 2 or i + length > len(options):
            break
        if kind == 2 and length >= 4:  # MSS
            mss = struct.unpack("!H", options[i + 2 : i + 4])[0]
            decoded_opts.append({"kind": "MSS", "value": mss})
        elif kind == 4:  # SACK_PERMITTED
            decoded_opts.append({"kind": "SACK_PERMITTED"})
        elif kind == 8:  # Timestamps
            ts_val = struct.unpack("!I", options[i + 2 : i + 6])[0]
            ts_ecr = struct.unpack("!I", options[i + 6 : i + 10])[0]
            decoded_opts.append(
                {"kind": "TS", "tsval": ts_val, "tsecr": ts_ecr}
            )
        else:
            decoded_opts.append({"kind": f"opt_{kind}"})
        i += length

    return (
        {
            "src_port": src_port,
            "dst_port": dst_port,
            "seq": seq,
            "ack": ack,
            "data_offset": data_offset // 4,
            "flags": tcp_flags_to_list(flags_bits),
            "flags_bits": f"0x{flags_bits:02x}",
            "window": window,
            "checksum": f"0x{checksum_in_segment:04x}",
            "checksum_ok": checksum_ok,
            "checksum_offloaded": checksum_offloaded,
            "urgent": urgent,
            "options": decoded_opts,
            "payload_len": len(payload),
        },
        payload,
    )


# ─── UDP (minimal) ───────────────────────────────────────────────
def parse_udp(segment: bytes) -> tuple[dict, bytes]:
    if len(segment) < 8:
        return ({"_error": "udp segment too short", "len": len(segment)}, b"")
    src_port = struct.unpack("!H", segment[0:2])[0]
    dst_port = struct.unpack("!H", segment[2:4])[0]
    length = struct.unpack("!H", segment[4:6])[0]
    payload = segment[8:length]
    return (
        {
            "src_port": src_port,
            "dst_port": dst_port,
            "length": length,
            "payload_len": len(payload),
        },
        payload,
    )


# ─── ARP (minimal) ───────────────────────────────────────────────
def parse_arp(packet: bytes) -> dict:
    if len(packet) < 28:
        return {"_error": "arp too short"}
    htype = struct.unpack("!H", packet[0:2])[0]
    ptype = struct.unpack("!H", packet[2:4])[0]
    hsize = packet[4]
    psize = packet[5]
    opcode = struct.unpack("!H", packet[6:8])[0]
    sender_mac = packet[8 : 8 + hsize]
    sender_ip = packet[8 + hsize : 8 + hsize + psize]
    target_mac = packet[8 + hsize + psize : 8 + 2 * hsize + psize]
    target_ip = packet[8 + 2 * hsize + psize : 8 + 2 * hsize + 2 * psize]
    return {
        "htype": htype,
        "ptype": f"0x{ptype:04x}",
        "hsize": hsize,
        "psize": psize,
        "opcode": opcode,
        "opcode_name": "request" if opcode == 1 else "reply" if opcode == 2 else str(opcode),
        "sender_mac": mac_bytes_to_str(sender_mac),
        "sender_ip": ipv4_to_str(sender_ip) if psize == 4 else sender_ip.hex(),
        "target_mac": mac_bytes_to_str(target_mac) if any(target_mac) else "?",
        "target_ip": ipv4_to_str(target_ip) if psize == 4 else target_ip.hex(),
    }


# ─── HTTP (best-effort, ASCII only) ───────────────────────────────
def parse_http(payload: bytes) -> Optional[dict]:
    """Decode a single HTTP request or response from a TCP payload.

    The shim only attempts to decode when the connection port is 80
    or 8080. Bodies are truncated to ~1 KB.
    """
    if not payload:
        return None
    try:
        text = payload.decode("ascii", errors="replace")
    except Exception:
        return None
    # Split headers/body at the first \r\n\r\n.
    sep = text.find("\r\n\r\n")
    if sep == -1:
        return None
    head = text[:sep]
    body = text[sep + 4 :]
    lines = head.split("\r\n")
    if not lines:
        return None
    start = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()

    truncated = False
    body_decoded: str
    if len(body) > 1024:
        body_decoded = body[:1024] + "…"
        truncated = True
    else:
        body_decoded = body

    out: dict[str, Any] = {
        "headers": headers,
        "body_decoded": body_decoded,
        "body_truncated": truncated,
    }

    if start.startswith("HTTP/"):
        # Response.
        parts = start.split(" ", 2)
        out["is_response"] = True
        out["is_request"] = False
        out["version"] = parts[0]
        out["status_code"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        out["status_text"] = parts[2] if len(parts) > 2 else ""
    else:
        # Request.
        parts = start.split(" ")
        out["is_request"] = True
        out["is_response"] = False
        out["method"] = parts[0] if len(parts) > 0 else None
        out["path"] = parts[1] if len(parts) > 1 else None
        out["version"] = parts[2] if len(parts) > 2 else None
    return out


# ─── Row summary builder ──────────────────────────────────────────
def build_summary(l2: dict, l3: Optional[dict], l4: Optional[dict], arp: Optional[dict]) -> str:
    """Build a one-line human-readable summary of this packet."""
    if arp is not None:
        op = arp.get("opcode_name", "?")
        if op == "request":
            return (
                f'ARP {arp["sender_ip"]} → * "who has {arp["target_ip"]}? '
                f'tell {arp["sender_mac"]}"'
            )
        else:
            return (
                f'ARP * → {arp["sender_ip"]} "{arp["sender_ip"]} is at '
                f'{arp["sender_mac"]}"'
            )
    if l4 is not None:
        sp = l4.get("src_port")
        dp = l4.get("dst_port")
        # Distinguish TCP from UDP by the presence of TCP-specific fields
        # (seq/ack/flags). The shim only emits `flags`/`seq`/`ack` for TCP,
        # so this discriminator is reliable.
        proto_name = "TCP" if (l4.get("flags") is not None or l4.get("seq") is not None) else "UDP"
        flags = ",".join(l4.get("flags", []))
        seq = l4.get("seq")
        ack = l4.get("ack")
        payload_len = l4.get("payload_len", 0)
        parts = [f"{proto_name} {sp} → {dp}"]
        if flags:
            parts.append(f"[{flags}]")
        if seq is not None:
            parts.append(f"seq={seq}")
        if ack is not None:
            parts.append(f"ack={ack}")
        if payload_len:
            parts.append(f"payload={payload_len} B")
        return " ".join(parts)
    if l3 is not None:
        proto = l3.get("protocol_name", "?")
        return f"{proto} {l3.get('src_ip', '?')} → {l3.get('dst_ip', '?')}"
    return f"frame len={l2.get('_raw_len', '?')}"


# ─── pcap stream parser ───────────────────────────────────────────
def parse_pcap_header(data: bytes) -> tuple[int, bool]:
    """Return (linktype, is_little_endian) from a pcap global header."""
    if len(data) < 24:
        raise ValueError("pcap header too short")
    magic = struct.unpack("<I", data[0:4])[0]
    if magic == PCAP_MAGIC_LE:
        le = True
    elif magic == PCAP_MAGIC_BE:
        le = False
    else:
        raise ValueError(f"not a pcap file (magic=0x{magic:08x})")
    endian = "<" if le else ">"
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    return linktype, le


def parse_one_packet(linktype: int, ts_sec: int, ts_usec: int, frame: bytes, pkt_id: int) -> dict:
    """Decode one frame into a PacketEvent."""
    l2, l3_or_arp = parse_l2(linktype, frame)
    l3: Optional[dict] = None
    l4: Optional[dict] = None
    arp: Optional[dict] = None
    l7: Optional[dict] = None
    src_ip_bytes = b""
    dst_ip_bytes = b""
    sections: list[dict] = []

    ethertype = l2.get("ethertype")
    if ethertype == ETHERTYPE_IPV4:
        l3, l4_or_icmp = parse_ipv4(l3_or_arp)
        proto = l3.get("protocol") if l3 else None
        # Reconstruct raw IP src/dst bytes for TCP pseudo-header.
        if l3:
            src_ip_bytes = bytes(int(x) for x in l3["src_ip"].split("."))
            dst_ip_bytes = bytes(int(x) for x in l3["dst_ip"].split("."))
        if proto == PROTO_TCP and l4_or_icmp:
            l4, payload = parse_tcp(l4_or_icmp, src_ip_bytes, dst_ip_bytes)
            # Best-effort HTTP decode if port is 80/8080.
            if l4 and l4.get("payload_len", 0) > 0 and (l4["src_port"] in (80, 8080) or l4["dst_port"] in (80, 8080)):
                l7 = parse_http(payload)
        elif proto == PROTO_UDP and l4_or_icmp:
            l4, _ = parse_udp(l4_or_icmp)
    elif ethertype == ETHERTYPE_ARP:
        arp = parse_arp(l3_or_arp)

    summary = build_summary(l2, l3, l4, arp)
    ts_str = (
        f"{ts_sec:04d}-"
        f"{(ts_sec % 31536000) // 3600:02d}-"  # rough HH (depends on epoch)
        "01-01"  # placeholder; we don't compute calendar here
    )
    # Use a stable ISO-like timestamp from epoch seconds.
    import datetime as _dt
    try:
        ts_str = (
            _dt.datetime.fromtimestamp(ts_sec, tz=_dt.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S")
            + f".{ts_usec:06d}Z"
        )
    except Exception:
        ts_str = f"epoch+{ts_sec}.{ts_usec:06d}"

    return {
        "id": pkt_id,
        "ts": ts_str,
        "ts_ns": ts_sec * 1_000_000_000 + ts_usec * 1_000,
        "iface": "any",
        "len": len(frame),
        "l2": {**l2, "crc_ok": True},
        "l3": l3,
        "l4": l4,
        "l7": l7,
        "summary": summary,
        "sections": sections,
    }


def iter_pcap(stream) -> Any:
    """Yield (ts_sec, ts_usec, frame_bytes) tuples from a binary pcap stream."""
    header = stream.read(24)
    if len(header) < 24:
        return
    linktype, le = parse_pcap_header(header)
    endian = "<" if le else ">"
    while True:
        rec = stream.read(16)
        if len(rec) < 16:
            return
        ts_sec, ts_usec, incl_len, _orig_len = struct.unpack(endian + "IIII", rec)
        frame = stream.read(incl_len)
        if len(frame) < incl_len:
            return
        yield ts_sec, ts_usec, frame


def main() -> int:
    """Stream-parse a binary pcap from stdin; emit NDJSON events to stdout.

    Designed for live capture: tcpdump writes binary pcap to its stdout
    (via `-w -`), this shim reads from stdin, parses one packet at a
    time, and writes each event to stdout immediately. A flush after
    each event keeps the file growing in real time so the backend can
    poll it with `docker exec cat`.
    """
    # Diagnostic banner — first line is always present in the output
    # file so we can tell whether the shim started at all.
    print("# capture_shim starting", file=sys.stderr, flush=True)
    pkt_id = 0
    stdin = sys.stdin.buffer

    # Read the 24-byte pcap global header.
    header = b""
    while len(header) < 24:
        chunk = stdin.read(24 - len(header))
        if not chunk:
            print(
                f"# capture_shim: EOF before pcap header ({len(header)}/24 bytes)",
                file=sys.stderr,
                flush=True,
            )
            return 0
        header += chunk
    try:
        linktype, le = parse_pcap_header(header)
    except ValueError as e:
        print(f"# error: {e}", file=sys.stderr, flush=True)
        return 1
    print(
        f"# capture_shim ready, linktype={linktype} endian={'LE' if le else 'BE'}",
        file=sys.stderr,
        flush=True,
    )
    endian = "<" if le else ">"

    while True:
        # Read a 16-byte pcap record header.
        rec = b""
        while len(rec) < 16:
            chunk = stdin.read(16 - len(rec))
            if not chunk:
                return 0
            rec += chunk
        ts_sec, ts_usec, incl_len, _ = struct.unpack(endian + "IIII", rec)
        frame = b""
        while len(frame) < incl_len:
            chunk = stdin.read(incl_len - len(frame))
            if not chunk:
                # Partial frame at EOF; emit what we have.
                break
            frame += chunk
        pkt_id += 1
        try:
            event = parse_one_packet(linktype, ts_sec, ts_usec, frame, pkt_id)
        except Exception as e:
            event = {
                "id": pkt_id,
                "ts": "1970-01-01T00:00:00.000000Z",
                "ts_ns": 0,
                "iface": "any",
                "len": len(frame),
                "l2": {"_error": str(e)},
                "l3": None,
                "l4": None,
                "l7": None,
                "summary": f"parse error: {e}",
                "sections": [],
            }
        sys.stdout.write(json.dumps(event, separators=(",", ":")))
        sys.stdout.write("\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
