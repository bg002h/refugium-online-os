#!/usr/bin/env python3
"""Count and classify guest egress using QEMU's independent Ethernet capture."""
import ipaddress
from pathlib import Path
import struct


def packets(path):
    with Path(path).open('rb') as f:
        head = f.read(24)
        end = {b'\xd4\xc3\xb2\xa1':'<', b'\xa1\xb2\xc3\xd4':'>'}[head[:4]]
        if struct.unpack_from(end+'I',head,20)[0] != 1:
            raise ValueError('Expected Ethernet capture')
        while header := f.read(16):
            if len(header) != 16:
                return
            _, _, size, _ = struct.unpack(end+'IIII', header)
            frame = f.read(size)
            if len(frame) != size:
                return
            yield frame


def audit(path):
    counts = {'outbound':0, 'arp':0, 'tor_tcp_443':0, 'other':0, 'received':0}
    for frame in packets(path):
        if frame[6:12] != bytes.fromhex('525400123456'):
            counts['received'] += 1
            continue
        counts['outbound'] += 1
        kind = frame[12:14]
        if kind == b'\x08\x06' and frame[28:32] == bytes([10,0,2,15]) and frame[38:42] == bytes([10,0,2,2]):
            counts['arp'] += 1
        elif kind == b'\x08\x00' and frame[23] == 6:
            start = 14+(frame[14]&15)*4
            port = int.from_bytes(frame[start+2:start+4],'big')
            dest = ipaddress.IPv4Address(frame[30:34])
            if port == 443 and dest.is_global:
                counts['tor_tcp_443'] += 1
            else:
                counts['other'] += 1
        else:
            counts['other'] += 1
    return counts


if __name__ == '__main__':
    import json,sys
    print(json.dumps(audit(sys.argv[1]),sort_keys=True))
