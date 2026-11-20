#!/usr/bin/env python3
"""Wait for new public signet blocks, compare the local view through Tor, then close the instance."""
import argparse
import json
from pathlib import Path
import time
from vm_session import Console, online, require
from vm_wire import audit


def observe(args):
    con = Console(args.socket)
    try:
        initial = con.ready()
        require(initial['mode'] == 'locked' and audit(args.capture)['outbound'] == 0, 'Cold cutoff')
        first, comparison = online(con, equality=True)
        start = time.monotonic()
        height = comparison['compared_height']
        print(json.dumps({'initial':first, 'match':comparison}), flush=True)
        while time.monotonic()-start < args.minutes*60:
            time.sleep(30)
            status = con.call('status')
            if status['mode'] != 'tor':
                raise RuntimeError(status)
            if status.get('node', {}).get('blocks',height) <= height:
                continue
            match = con.call('compare',timeout=125)
            if 'error' in match:
                print(json.dumps(match), flush=True)
                continue
            require(match['same_block'], 'Observed conflicting block hashes')
            if match['compared_height'] <= height:
                continue
            height = match['compared_height']
            print(json.dumps({'elapsed_s':round(time.monotonic()-start), 'match':match}), flush=True)
            if height >= comparison['compared_height'] + args.blocks:
                break
        require(height >= comparison['compared_height']+args.blocks, 'Insufficient new blocks in observation window')
    finally:
        try:
            con.call('lock')
            cut = audit(args.capture)
            time.sleep(10)
            after = audit(args.capture)
            require(cut['outbound']==after['outbound'] and after['other']==0,'Post-cut movement')
            print(json.dumps({'cut':cut,'after':after}),flush=True)
            print(con.call('poweroff'),flush=True)
        finally:
            con.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('socket',type=Path)
    p.add_argument('capture',type=Path)
    p.add_argument('--blocks',type=int,default=2)
    p.add_argument('--minutes',type=int,default=60)
    observe(p.parse_args())
