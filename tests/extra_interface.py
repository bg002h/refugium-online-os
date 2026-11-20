#!/usr/bin/env python3
"""Present an unexpected second adapter and check both sides from the host."""
import argparse
from pathlib import Path
import runpy
import subprocess
import sys
import time
from unittest.mock import patch

from vm_session import Console, require
from vm_wire import packets

ROOT=Path(__file__).resolve().parents[1]


def launch(image,state):
    original=subprocess.Popen
    def extra_device(argv,*args,**kwargs):
        if argv[0]=='qemu-system-x86_64':
            argv=[*argv,'-netdev','user,id=extra,restrict=on,ipv6=off',
                  '-device','virtio-net-pci,netdev=extra,romfile=',
                  '-object','filter-dump,id=extra_capture,netdev=extra,maxlen=96,file='+str(state/'extra.pcap')]
        return original(argv,*args,**kwargs)
    sys.path.insert(0,str(ROOT/'scripts'))
    sys.argv=[str(ROOT/'scripts/run'),str(image),str(state),'--serial-socket',str(state/'serial.sock'),
              '--capture',str(state/'first.pcap')]
    with patch('subprocess.Popen',side_effect=extra_device):
        runpy.run_path(sys.argv[0],run_name='__main__')


def exercise(image,state):
    state.mkdir(mode=0o700)
    p=subprocess.Popen([sys.executable,'-B',__file__,image,state,'--launch'])
    serial=state/'serial.sock'
    deadline=time.monotonic()+30
    while not serial.exists() and time.monotonic()<deadline and p.poll() is None:
        time.sleep(.2)
    con=Console(serial)
    try:
        status=con.ready()
        require(status['mode']=='locked' and 'Multiple adapters' in status['issue'],'Missing refusal')
        require('Multiple adapters' in con.call('connect')['error'],'Unexpected activation')
        require(status['node']['chain']=='signet','Local RPC unavailable')
        time.sleep(5)
        require(all(not any(packets(state/name)) for name in ('first.pcap','extra.pcap')),
                'Unexpected frames on at least one adapter')
        print('PASS: multiple adapters refused, local signet available, neither captured a frame',flush=True)
    finally:
        con.call('poweroff')
        con.close()
        p.wait(timeout=45)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('new_state',type=Path)
    parser.add_argument('--launch',action='store_true',help=argparse.SUPPRESS)
    opts=parser.parse_args()
    (launch if opts.launch else exercise)(opts.image.resolve(),opts.new_state.resolve())
