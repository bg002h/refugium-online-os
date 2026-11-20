#!/usr/bin/env python3
"""Exercise the host seal after this test intentionally terminates its own launcher."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

from vm_session import Console, require

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hostgate import active, Monitor


def exercise(image,state):
    state.mkdir(mode=0o700)
    serial = state/'serial.sock'
    launcher = subprocess.Popen([ROOT/'scripts/run', image, state, '--serial-socket', serial])
    con = None
    try:
        limit = time.monotonic()+30
        while not serial.exists() and time.monotonic()<limit and launcher.poll() is None:
            time.sleep(.1)
        con = Console(serial)
        require(con.ready()['mode']=='locked','Initial guest state')
        with Monitor(state) as mon:
            require(mon.has_backend(), 'Missing starting uplink')
        launcher.terminate()
        launcher.wait(timeout=5)
        require(active(state),'QEMU did not keep its instance lock')
        denied=subprocess.run([ROOT/'scripts/gate','arm',state],capture_output=True,text=True)
        require(denied.returncode != 0 and 'Power off' in denied.stderr, 'Running re-arm')
        subprocess.run([ROOT/'scripts/gate','seal',state],check=True)
        with Monitor(state) as mon:
            require(not mon.has_backend(),'Backend remained after external cutoff')
        require('error' in con.call('connect'), 'Guest bypassed seal')
        print('PASS: QEMU retained the lock, running re-arm refused, external seal removed the backend',
              flush=True)
    finally:
        if con:
            try:
                con.call('poweroff')
            finally:
                con.close()
        if launcher.poll() is None:
            launcher.wait(timeout=45)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('new_state',type=Path)
    opts=p.parse_args()
    exercise(opts.image.resolve(),opts.new_state.resolve())
