#!/usr/bin/env python3
"""Exercise a dedicated, freshly booted VM via its serial socket and external capture."""
import argparse
from collections import deque
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

from vm_wire import audit


class Console:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(str(path))
        self.sock.settimeout(1)
        self.buffer = b''
        self.recent = deque(maxlen=12)

    def send(self, cmd):
        self.sock.sendall((cmd+'\n').encode())

    def receive(self, timeout=20):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            while b'\n' in self.buffer:
                line,self.buffer = self.buffer.split(b'\n',1)
                self.recent.append(line[-300:].decode(errors='replace').strip())
                try:
                    result = json.loads(line.strip())
                    if isinstance(result,dict):
                        return result
                except (ValueError,UnicodeError):
                    pass
            try:
                chunk=self.sock.recv(8192)
            except TimeoutError:
                continue
            if not chunk:
                raise EOFError('Console closed')
            self.buffer+=chunk
        raise TimeoutError('No console reply')

    def call(self, cmd, timeout=20):
        self.send(cmd)
        return self.receive(timeout)

    def ready(self):
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                status = self.call('status', timeout=5)
                if 'mode' in status and 'node' in status:
                    if status['mode'] == 'locked':
                        # Firmware or early storage setup may queue multiple status
                        # lines. A side-effect-free refusal delimits their replies.
                        self.send('compare')
                        while time.monotonic() < deadline:
                            reply = self.receive(timeout=10)
                            if reply.get('error') == 'Outbound traffic is locked':
                                return status
                        raise TimeoutError('No locked startup response delimiter')
                    return status
            except TimeoutError:
                pass
        raise TimeoutError('Guest console and local Core RPC did not become ready. Recent lines: ' + repr(list(self.recent)))

    def close(self):
        self.sock.close()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def online(console, equality=False, compare=True):
    require(console.call('connect').get('mode')=='tor','Tor activation failed')
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        status=console.call('status')
        print(json.dumps({'tor':status.get('tor_bootstrap'), 'peers':status.get('peers'), 'height':status.get('node',{}).get('blocks')}),file=sys.stderr,flush=True)
        if status['mode']!='tor':
            raise RuntimeError(status)
        if status.get('tor_bootstrap')=='100%' and status.get('peers',0)>0:
            if not compare:
                return status, None
            if equality or status.get('node',{}).get('headers',0)>0:
                result=console.call('compare',timeout=125)
                if 'error' in result:
                    print(json.dumps(result),file=sys.stderr,flush=True)
                if 'error' in result and equality:
                    time.sleep(8)
                    continue
                if result.get('same_block') and (not equality or
                    (not result['initial_sync'] and result['local_height']>=result['explorer_height'])):
                    return status,result
        time.sleep(4)
    raise RuntimeError('Timed out waiting for public signet and explorer agreement')


def run(args):
    con=Console(args.socket)
    try:
        initial=con.ready()
        require(initial['mode']=='locked' and not initial['link_up'] and initial['node']['chain']=='signet','Initial state')
        require(audit(args.capture)['outbound']==0 and audit(args.capture)['received']==0,'Frames during locked boot')
        require('locked' in con.call('compare')['error'],'Explorer active while locked')
        first, comparison=online(con,args.synced)
        print(json.dumps({'online':first,'comparison':comparison}),flush=True)
        # A new comparison races the cut, so a queued GET and established peer sessions are both in scope.
        con.send('compare')
        con.send('lock')
        replies=[con.receive(125),con.receive(125)]
        require(any(r.get('mode')=='locked' for r in replies),'Lock did not acknowledge')
        require(con.call('status')['link_up'] is False,'Adapter still up')
        before=audit(args.capture)
        time.sleep(10)
        after=audit(args.capture)
        require(before['outbound']==after['outbound'] and before['tor_tcp_443']>0 and after['other']==0,
                'Unexpected guest egress after cutoff')
        print(json.dumps({'guest_lock_before':before,'guest_lock_after':after}),flush=True)
        second, _=online(con,compare=False)
        gate=Path(__file__).resolve().parents[1]/'scripts/gate'
        subprocess.run([gate,'seal',args.state],check=True)
        if subprocess.run([gate,'arm',args.state],capture_output=True).returncode==0:
            raise RuntimeError('Re-arm allowed on a running VM')
        before=audit(args.capture)
        time.sleep(10)
        after=audit(args.capture)
        require(before==after and after['other']==0,'Frames after removing host backend')
        require(con.call('status')['mode']=='locked','Guest missed host cutoff')
        require('error' in con.call('connect'),'Guest reconnected through the host cutoff')
        print(json.dumps({'second':second,'host_seal_before':before,'host_seal_after':after}),flush=True)
        print(con.call('poweroff'),flush=True)
    finally:
        con.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('socket',type=Path)
    p.add_argument('capture',type=Path)
    p.add_argument('state',type=Path)
    p.add_argument('--synced',action='store_true',help='require a tip comparison using a pre-synced test disk')
    run(p.parse_args())
