"""Read host-to-guest datagrams and deliver them to the receiver on guest loopback."""
from pathlib import Path
import socket
import struct
import sys
import time


def main():
    stream = sys.stdin.buffer
    heartbeat = Path('/run/radio/last-datagram')
    last_update = -5.0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton('127.0.0.1'))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 0)
        while header := stream.read(2):
            if len(header) != 2:
                return
            length, = struct.unpack('!H', header)
            data = stream.read(length)
            if len(data) != length:
                return
            if 0 < length <= 2048:
                sock.sendto(data, ('239.0.0.2', 4434))
                now = time.monotonic()
                if now - last_update >= 5:
                    heartbeat.touch()
                    last_update = now


if __name__ == '__main__':
    main()
