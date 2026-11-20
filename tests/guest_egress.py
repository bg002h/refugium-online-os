"""Synthetic-network test init. This file is added only to a disposable test initramfs."""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, '/usr/lib/refugium-online')
import firewall
from settings import ARCHIVE, BITCOIN, FILTER, INDEXER, LOCAL_WEB, MEMPOOL, OPERATOR, RADIO, RELAY, SATELLITE, TOR, WEB

SERVICES = (0, TOR, FILTER, BITCOIN, WEB, OPERATOR, ARCHIVE, SATELLITE, RELAY, RADIO)
DESKTOP = Path('/etc/refugium-online/desktop').exists()
PORTS = (9050, 9051, 38332, 8332, 8432)
if DESKTOP:
    SERVICES += (INDEXER, MEMPOOL, LOCAL_WEB)
    PORTS += (3000, 8080, 8081, 8999, 50001, 4224)


def try_connect(host, port):
    with socket.socket() as s:
        s.settimeout(.2)
        return s.connect_ex((host,port)) == 0


def probe(uid, phase):
    local=[port for port in PORTS if try_connect('127.0.0.1',port)]
    # The QEMU test backend has restrict=on. These frames cannot reach any real host.
    # Distinct destination suffixes let the external capture identify each attempt.
    base={'locked':30,'enabled':20,'relocked':40}[phase]
    addr='93.184.216.'+str(base+uid-TOR if uid else base-1)
    try_connect(addr, 443)
    try_connect(addr,80)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        try:
            udp.sendto(b'fixture',(addr,53))
        except PermissionError:
            pass
    print(json.dumps(local))


def main():
    dev=next(p.name for p in Path('/sys/class/net').iterdir() if p.name!='lo')
    ip=lambda *args:subprocess.run(['ip',*args],check=True)
    def ping(host):
        return subprocess.run(['ping','-4','-n','-c','1','-W','1',host], user=OPERATOR,
                              group=OPERATOR, extra_groups=[], capture_output=True, timeout=5)

    ip('link','set','lo','up')
    # Positive control with only loopback up in the disposable test guest.
    loopback = ping('127.0.0.1')
    assert loopback.returncode == 0, (loopback.stdout, loopback.stderr)
    firewall.install(dev,False)
    ip('addr','add','10.0.2.15/24','dev',dev)
    ip('link','set','dev',dev,'up')
    ip('route','add','default','via','10.0.2.2','dev',dev)
    ports=[]
    for port in PORTS:
        srv=socket.socket()
        srv.bind(('127.0.0.1',port))
        srv.listen(50)
        ports.append(srv)
    disabled_families=[]
    for family in (socket.AF_INET6,socket.AF_PACKET):
        try:
            s=socket.socket(family,socket.SOCK_DGRAM)
        except OSError as e:
            if e.errno==errno.EAFNOSUPPORT:
                disabled_families.append(family.name)
        else:
            s.close()
    assert len(disabled_families)==2, disabled_families
    for phase in ('locked','enabled','relocked'):
        firewall.install(dev,phase=='enabled')
        for target in ('127.0.0.1', '93.184.216.77'):
            blocked = ping(target)
            assert blocked.returncode == 1, (phase, target, blocked.stdout, blocked.stderr)
        def check(uid):
            raw=subprocess.check_output([sys.executable,'-B',__file__,'--probe',str(uid),phase],
                                        user=uid,group=uid,extra_groups=[],stderr=subprocess.STDOUT)
            allowed=set(json.loads(raw))
            expected={38332} if uid in (0,BITCOIN,WEB) else set()
            if uid in (0, RELAY):
                expected.update((8332, 8432))
            if phase=='enabled' and uid==FILTER:
                expected.update((9050,9051))
            if DESKTOP:
                if uid in (0, OPERATOR):
                    expected.update((8080, 8081, 38332))
                if uid in (INDEXER, MEMPOOL):
                    expected.add(8332)
                if uid in (0, LOCAL_WEB, MEMPOOL):
                    expected.add(3000)
                if uid == LOCAL_WEB:
                    expected.add(8999)
            assert allowed==expected,(phase,uid,allowed,expected)
        with ThreadPoolExecutor(max_workers=len(SERVICES)) as workers:
            list(workers.map(check, SERVICES))
    print('EGRESS-PASS '+json.dumps({'uid_count':len(SERVICES),'phases':3,'unavailable':disabled_families}),flush=True)


if __name__=='__main__':
    if '--probe' in sys.argv:
        probe(int(sys.argv[2]),sys.argv[3])
    else:
        try:
            main()
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            os.sync()
            ctypes.CDLL(None).reboot(0x4321FEDC)
