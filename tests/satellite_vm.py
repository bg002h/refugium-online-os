"""Replay FIBRE datagrams into a dedicated sealed VM or check its subsequent boot."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

from vm_session import Console, require

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'scripts'))
from hostgate import Monitor

TIP = '0000000082b5015589a3fdf2d4baff403e6f0be035a5d9742c1cae6295464449'


def transmit(state):
    subprocess.run(['ip','link','set','lo','up'],check=True)
    subprocess.run(['ip','route','add','239.0.0.2/32','dev','lo','src','127.0.0.1'],check=True)
    forward = subprocess.Popen([REPO/'scripts/radio',state,'--interface','127.0.0.1','--source','127.0.0.1'])
    try:
        packets = []
        with gzip.open(REPO/'tests/fixtures/mainnet-radio.gz','rb') as inp:
            while header := inp.read(2):
                size, = struct.unpack('!H',header)
                payload = inp.read(size)
                require(0 < size <= 2048 and len(payload) == size,'Incomplete fixture')
                packets.append(payload)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton('127.0.0.1'))
            udp.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,0)
            time.sleep(.3)
            for _ in range(3):
                require(forward.poll() is None, 'Host radio adapter exited')
                for data in packets:
                    udp.sendto(data,('239.0.0.2',4434))
                    time.sleep(.012)
    finally:
        forward.terminate()
        forward.wait()


def check(console, state, persisted):
    prev = bytes.fromhex('000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f')[::-1]
    blocks = (REPO/'tests/fixtures/mainnet-first-three.hex').read_text().splitlines()
    require(len(blocks) == 3, 'Historical input count')
    for line in blocks:
        block = bytes.fromhex(line)
        require(block[4:36] == prev, 'Historical input parent hash')
        prev = hashlib.sha256(hashlib.sha256(block[:80]).digest()).digest()
    require(prev[::-1].hex() == TIP, 'Historical input tip')
    with Monitor(state) as monitor:
        require(not monitor.has_backend() and not monitor.command('query-rx-filter'),'Unexpected WAN hardware')
    con = Console(console)
    try:
        status = con.ready()
        main = status['mainnet']
        require(not status['issue'] and not main.get('issues'),status)
        require(main['archive']['pruned'] is False and main['satellite']['pruned'] is True,main)
        require(status['mode']=='locked' and status['uplink'] is None and main['radio_input'],status)
        require('error' in con.call('connect'),'Connected from a sealed guest')
        if not persisted:
            require(all(main[role]['blocks']==0 for role in ('archive','satellite')),main)
            subprocess.run(['bwrap','--unshare-user','--uid','0','--gid','0','--unshare-net','--cap-add',
                            'CAP_NET_ADMIN','--ro-bind','/','/','--dev','/dev','--proc','/proc','--bind',state,state,
                            sys.executable,'-B',__file__,'--transmit',str(console),str(state)],check=True)
        deadline = time.monotonic()+65
        while True:
            status = con.call('status')
            main = status['mainnet']
            if all(main[role].get('bestblockhash')==TIP for role in ('archive','satellite')):
                break
            require(time.monotonic() < deadline, status)
            time.sleep(.5)
        require(all(main[role]['blocks']==3 and main[role]['chain']=='main' for role in ('archive','satellite')),main)
        require(status['node']['chain']=='signet' and status['node']['blocks']==0 and status['peers']==0,status)
        require(persisted == (main['radio_last_datagram_age_seconds'] is None),main)
        print(json.dumps(status,sort_keys=True),flush=True)
        require(con.call('poweroff').get('mode')=='shutting down','Shutdown failed')
    finally:
        con.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('console',type=Path)
    p.add_argument('state',type=Path)
    p.add_argument('--persisted',action='store_true')
    p.add_argument('--transmit',action='store_true',help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.transmit:
        transmit(a.state.resolve())
    else:
        check(a.console,a.state.resolve(),a.persisted)
