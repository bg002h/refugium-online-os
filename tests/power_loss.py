#!/usr/bin/env python3
"""Cut power to a dedicated connected instance and verify the next boot starts locked."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
from vm_session import Console, require
from vm_wire import audit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from hostgate import Monitor


def start(image,state,epoch):
    path=state/(epoch+'.sock')
    pcap=state/(epoch+'.pcap')
    proc=subprocess.Popen([ROOT/'scripts/run',image,state,'--serial-socket',path,'--capture',pcap])
    limit=time.monotonic()+30
    while not path.exists() and time.monotonic()<limit and proc.poll() is None:
        time.sleep(.1)
    con=Console(path)
    status=con.ready()
    require(status['mode']=='locked' and status['link_up'] is False,'Startup allowed traffic')
    require(audit(pcap)['outbound']==0,'Frames during cold boot')
    return proc,con,pcap


def exercise(image,state):
    state.mkdir(mode=0o700)
    first,con,pcap=start(image,state,'before')
    try:
        require(con.call('connect')['mode']=='tor','No network activation')
        limit=time.monotonic()+60
        while time.monotonic()<limit and audit(pcap)['tor_tcp_443']==0:
            time.sleep(.5)
        require(audit(pcap)['tor_tcp_443']>0,'Cut happened before Tor sent traffic')
        with Monitor(state) as mon:
            mon.command('quit')
        first.wait(timeout=30)
    finally:
        con.close()
    second,con,after=start(image,state,'after')
    try:
        require('locked' in con.call('compare')['error'],'Explorer available after abrupt restart')
        require(con.call('status')['node']['chain']=='signet','Local Core failed to recover')
        require(audit(after)['outbound']==0,'Post-restart egress')
        print('PASS: cut power during Tor traffic; rebooted with zero outbound frames and local signet RPC',
              flush=True)
    finally:
        con.call('poweroff')
        con.close()
        second.wait(timeout=45)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('new_state',type=Path)
    opts=p.parse_args()
    exercise(opts.image.resolve(),opts.new_state.resolve())
