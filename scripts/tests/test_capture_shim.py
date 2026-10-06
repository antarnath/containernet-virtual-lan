"""Offline test for host-agent/capture_shim.py.

Builds a synthetic pcap file with one ARP request, one ARP reply,
a TCP SYN/SYN-ACK/ACK handshake, and a TCP PSH-ACK carrying an
HTTP POST request, then runs the shim and asserts that all
checksums decode correctly.
"""
import json
import struct
import subprocess
import sys

SHIM = "/media/antar-chandra-nath/Media/Personal/ContainerNet/host-agent/capture_shim.py"


def internet_checksum(data):
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def pcap_global_header():
    return struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)


def pcap_record(ts_sec, ts_usec, frame):
    return struct.pack("<IIII", ts_sec, ts_usec, len(frame), len(frame)) + frame


def eth(dst, src, et):
    return dst + src + struct.pack("!H", et)


def ip_with_checksum(src, dst, proto, payload):
    total_length = 20 + len(payload)
    hdr_no_cksum = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, total_length, 0x4F12, 0x4000,
        64, proto, 0,
        bytes(int(x) for x in src.split(".")),
        bytes(int(x) for x in dst.split(".")),
    )
    cksum = internet_checksum(hdr_no_cksum)
    hdr = hdr_no_cksum[:10] + struct.pack("!H", cksum) + hdr_no_cksum[12:]
    return hdr + payload


def tcp_with_checksum(sp, dp, seq, ack, flags_byte, src_ip, dst_ip, payload):
    data_off = 8  # 32-byte header (20 base + 12 options/padding)
    options = b"\x02\x04\x05\xb4" + b"\x00" * 8  # MSS=1460 + padding
    hdr_no_cksum = struct.pack(
        "!HHIIBBHHH",
        sp, dp, seq, ack,
        (data_off << 4), flags_byte,
        65535, 0, 0,
    ) + options
    pseudo = (
        bytes(int(x) for x in src_ip.split("."))
        + bytes(int(x) for x in dst_ip.split("."))
        + b"\x00"
        + bytes([6])
        + struct.pack("!H", len(hdr_no_cksum) + len(payload))
    )
    cksum = internet_checksum(pseudo + hdr_no_cksum + payload)
    hdr = hdr_no_cksum[:16] + struct.pack("!H", cksum) + hdr_no_cksum[18:]
    return hdr + payload


def main():
    frames = []

    arp_req = struct.pack(
        "!HHBBH6s4s6s4s",
        1, 0x0800, 6, 4, 1,
        b"\xaa\xbb\xcc\x00\x00\x04",
        bytes([10, 30, 0, 4]),
        b"\x00" * 6,
        bytes([10, 30, 0, 5]),
    )
    frames.append(
        eth(b"\xff" * 6, b"\xaa\xbb\xcc\x00\x00\x04", 0x0806) + arp_req
    )

    arp_rep = struct.pack(
        "!HHBBH6s4s6s4s",
        1, 0x0800, 6, 4, 2,
        b"\xaa\xbb\xcc\x00\x00\x05",
        bytes([10, 30, 0, 5]),
        b"\xaa\xbb\xcc\x00\x00\x04",
        bytes([10, 30, 0, 4]),
    )
    frames.append(
        eth(b"\xaa\xbb\xcc\x00\x00\x04", b"\xaa\xbb\xcc\x00\x00\x05", 0x0806) + arp_rep
    )

    syn = tcp_with_checksum(42318, 8080, 100, 0, 0x02, "10.30.0.4", "10.30.0.5", b"")
    frames.append(
        eth(b"\xaa\xbb\xcc\x00\x00\x05", b"\xaa\xbb\xcc\x00\x00\x04", 0x0800)
        + ip_with_checksum("10.30.0.4", "10.30.0.5", 6, syn)
    )

    synack = tcp_with_checksum(8080, 42318, 300, 101, 0x12, "10.30.0.5", "10.30.0.4", b"")
    frames.append(
        eth(b"\xaa\xbb\xcc\x00\x00\x04", b"\xaa\xbb\xcc\x00\x00\x05", 0x0800)
        + ip_with_checksum("10.30.0.5", "10.30.0.4", 6, synack)
    )

    ackpkt = tcp_with_checksum(42318, 8080, 101, 301, 0x10, "10.30.0.4", "10.30.0.5", b"")
    frames.append(
        eth(b"\xaa\xbb\xcc\x00\x00\x05", b"\xaa\xbb\xcc\x00\x00\x04", 0x0800)
        + ip_with_checksum("10.30.0.4", "10.30.0.5", 6, ackpkt)
    )

    http_body = (
        b"POST /send HTTP/1.1\r\n"
        b"Host: 10.30.0.5:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 47\r\n"
        b"\r\n"
        b'{"from":"host-1","to":"host-2","body":"hi","protocol":"tcp"}'
    )
    psh = tcp_with_checksum(
        42318, 8080, 101, 301, 0x18, "10.30.0.4", "10.30.0.5", http_body
    )
    frames.append(
        eth(b"\xaa\xbb\xcc\x00\x00\x05", b"\xaa\xbb\xcc\x00\x00\x04", 0x0800)
        + ip_with_checksum("10.30.0.4", "10.30.0.5", 6, psh)
    )

    with open("/tmp/sample.pcap", "wb") as f:
        f.write(pcap_global_header())
        for i, fr in enumerate(frames):
            f.write(pcap_record(0, i * 1000, fr))

    out = subprocess.run(
        ["python3", SHIM],
        stdin=open("/tmp/sample.pcap", "rb"),
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print("FAIL rc=", out.returncode, file=sys.stderr)
        print(out.stderr, file=sys.stderr)
        return 1

    lines = out.stdout.strip().split("\n")
    print(f"Got {len(lines)} events")
    assert len(lines) == 6, f"expected 6 events, got {len(lines)}"

    expected_flags = [
        None,
        None,
        ["SYN"],
        ["SYN", "ACK"],
        ["ACK"],
        ["PSH", "ACK"],
    ]
    for ln, want in zip(lines, expected_flags):
        e = json.loads(ln)
        print(f"  #{e['id']:>2} {e['summary']}")
        if e.get("l3"):
            assert e["l3"]["checksum_ok"], f"#{e['id']} ip checksum mismatch"
        if e.get("l4"):
            assert e["l4"]["checksum_ok"], f"#{e['id']} tcp checksum mismatch"
            got = e["l4"]["flags"]
            assert got == want, f"#{e['id']} flags {got} != {want}"
        if e["id"] == 6:
            assert e.get("l7") is not None, "HTTP not decoded"
            assert e["l7"].get("method") == "POST", e["l7"]
            assert e["l7"].get("path") == "/send", e["l7"]
            assert "host-1" in e["l7"]["body_decoded"], e["l7"]
    print("ALL CHECKSUMS OK, ALL FLAGS CORRECT, HTTP DECODED")

    # ─── SLL2 (linktype 276) path — what we actually use in containers ─
    sll2_frames = []
    sll2_header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 276)
    # SLL2 header: protocol(2) + reserved(2) + addr_len(1) + addr(8) + pad(7) = 20
    def sll2_wrap(ethertype, sender_mac, payload):
        sll2 = (
            struct.pack("!H", ethertype)
            + b"\x00\x00"          # reserved
            + bytes([8])           # addr length (padded)
            + sender_mac.ljust(8, b"\x00")  # 8-byte address
            + b"\x00" * 7          # pad
        )
        assert len(sll2) == 20, len(sll2)
        return sll2 + payload

    arp_req_eth = eth(b"\xff" * 6, b"\xaa\xbb\xcc\x00\x00\x04", 0x0806) + arp_req
    sll2_frames.append(
        sll2_wrap(0x0806, b"\xaa\xbb\xcc\x00\x00\x04", arp_req_eth[14:])
    )
    tcp_psh_eth = eth(b"\xaa\xbb\xcc\x00\x00\x05", b"\xaa\xbb\xcc\x00\x00\x04", 0x0800) + ip_with_checksum("10.30.0.4", "10.30.0.5", 6, psh)
    # The SLL2 header's "protocol" is what was inside the frame: 0x0800 = IPv4
    sll2_frames.append(
        sll2_wrap(0x0800, b"\xaa\xbb\xcc\x00\x00\x04", tcp_psh_eth[14:])
    )

    with open("/tmp/sll2.pcap", "wb") as f:
        f.write(sll2_header)
        for i, fr in enumerate(sll2_frames):
            f.write(pcap_record(0, i * 1000, fr))

    out2 = subprocess.run(
        ["python3", SHIM],
        stdin=open("/tmp/sll2.pcap", "rb"),
        capture_output=True,
        text=True,
    )
    assert out2.returncode == 0, f"sll2 rc={out2.returncode}: {out2.stderr}"
    sll2_lines = out2.stdout.strip().split("\n")
    print(f"SLL2: {len(sll2_lines)} events")
    assert len(sll2_lines) == 2, f"expected 2 sll2 events, got {len(sll2_lines)}"
    e0 = json.loads(sll2_lines[0])
    e1 = json.loads(sll2_lines[1])
    assert e0["l2"]["linktype"] == 276, e0["l2"]
    assert e0["l2"]["src_mac"] == "aa:bb:cc:00:00:04", e0["l2"]
    assert "ARP" in e0["summary"], e0
    assert e1["l2"]["linktype"] == 276, e1["l2"]
    assert e1["l4"]["flags"] == ["PSH", "ACK"], e1["l4"]
    assert e1["l4"]["checksum_ok"], e1["l4"]
    assert e1["l3"]["checksum_ok"], e1["l3"]
    print("SLL2 PATH OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
