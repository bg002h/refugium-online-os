#!/usr/bin/env python3
"""Check an actual sealed boot using the serial console and independent machine monitor."""
import argparse
from pathlib import Path
import sys
import time
from vm_session import Console, require

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from hostgate import Monitor

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('socket',type=Path)
    p.add_argument('state',type=Path)
    opts=p.parse_args()
    con=Console(opts.socket)
    try:
        with Monitor(opts.state) as mon:
            require(not mon.has_backend(), 'A user-mode network exists')
            require(not mon.command('query-rx-filter'), 'A network adapter exists')
        status=con.ready()
        require(status['mode']=='locked' and status['uplink'] is None,'Sealed status')
        require(status['node']['chain']=='signet','Local signet RPC unavailable')
        require('error' in con.call('connect') and 'locked' in con.call('compare')['error'],'Unexpected external access')
        print('PASS: no adapter or backend, guest connect refused, local signet RPC available',flush=True)
        print(con.call('poweroff'),flush=True)
    finally:
        con.close()
