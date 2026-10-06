import struct, sys, json
sys.path.insert(0, '/media/antar-chandra-nath/Media/Personal/ContainerNet/host-agent')
from capture_shim import internet_checksum

src_ip = bytes([10, 101, 0, 11])
dst_ip = bytes([10, 101, 0, 12])
pseudo = src_ip + dst_ip + bytes([0, 6]) + struct.pack('!H', 40)

with open('/tmp/offload.json') as f:
    d = json.load(f)
syn = next((e for e in d['events'] if (e.get('l4') or {}).get('flags') == ['SYN']), None)
print('captured checksum:', syn['l4']['checksum'])
seg0_16 = struct.pack('!HHII', syn['l4']['src_port'], syn['l4']['dst_port'], syn['l4']['seq'], syn['l4']['ack'])
data_off_flags = (syn['l4']['data_offset'] << 12) + 0x002
seg0_16 += struct.pack('!HH', data_off_flags, syn['l4']['window'])

def raw_sum(data):
    if len(data) % 2:
        data = data + b'\x00'
    s = 0
    for i in range(0, len(data), 2):
        s = s + ((data[i] << 8) | data[i + 1])
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return s & 0xFFFF

raw_pseudo_only = raw_sum(pseudo)
print('pseudo-only raw sum:', hex(raw_pseudo_only))
print('pseudo-only ~raw:', hex((~raw_pseudo_only) & 0xFFFF))

# Test multiple hypotheses
print('Hypothesis A: ~pseudo == captured:', ((~raw_pseudo_only) & 0xFFFF) == captured)

# Try adding just src_port+dst_port
pseudo2 = pseudo + struct.pack('!HH', syn['l4']['src_port'], syn['l4']['dst_port'])
raw_2 = raw_sum(pseudo2)
print('pseudo+sport+dport raw:', hex(raw_2))
print('Hypothesis B: ~raw_2 == captured:', ((~raw_2) & 0xFFFF) == captured)

# pseudo + first 12 bytes (sport+dport+seq+ack)
pseudo3 = pseudo + seg0_16[:12]
raw_3 = raw_sum(pseudo3)
print('pseudo+first12 raw:', hex(raw_3))
print('Hypothesis C: ~raw_3 == captured:', ((~raw_3) & 0xFFFF) == captured)

# pseudo + first 16 bytes (without window)
pseudo4 = pseudo + seg0_16[:16]
raw_4 = raw_sum(pseudo4)
print('pseudo+first16 raw:', hex(raw_4))
print('Hypothesis D: ~raw_4 == captured:', ((~raw_4) & 0xFFFF) == captured)

# All of pseudo+seg0_16
raw_5 = raw_sum(pseudo + seg0_16)
print('pseudo+seg0_16 raw:', hex(raw_5))
print('Hypothesis E: ~raw_5 == captured:', ((~raw_5) & 0xFFFF) == captured)

# What's actually in 0x150f? Let me check if it's a precomputed value
print()
print('captured 0x150f as 16-bit words:')
print('  byte[0:2]:', hex(((captured >> 8) & 0xFF)))
print('  byte[1]:', hex(captured & 0xFF))
