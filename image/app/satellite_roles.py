"""Lifecycle of the two isolated mainnet services on the permanent mainnet disk."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from settings import APP, ARCHIVE, ARCHIVE_PEERS, RADIO, RELAY, SATELLITE

BASE = Path('/etc/refugium-online')
VOLUME = Path('/mainnet')
RELAY_DIR = Path('/run/blockrelay')
ROLES = {'archive':(ARCHIVE,'/usr/local/bin/bitcoind','mainnet.conf',8332),
         'satellite':(SATELLITE,'/usr/local/libexec/bitcoin-satellite','satellite.conf',8432)}


def cli(name, method, *switches):
    port = ROLES[name][3]
    return ['/usr/local/bin/bitcoin-cli','-datadir=/run/bitcoin-client','-rpcconnect=127.0.0.1',
            '-rpcport='+str(port),'-rpccookiefile=/run/'+name+'/.cookie',*switches,method]


class Mainnet:
    def __init__(self):
        self.procs = {}
        self.issues = {}
        self.mounted = False
        self.radio = None
        self.relay = None

    def start(self, directory, daemon, launch):
        devices = subprocess.run(['blkid','-t','LABEL=RO_MAINNET','-o','device'],
                                 text=True,capture_output=True).stdout.splitlines()
        if len(devices) != 1:
            self.issues['storage'] = 'One RO_MAINNET data disk required'
            return
        VOLUME.mkdir(exist_ok=True)
        subprocess.run(['mount','-t','ext4','-o','nodev,nosuid,noexec,noatime',devices[0],VOLUME],check=True)
        self.mounted = True
        os.chown(VOLUME, 0, 0)
        os.chmod(VOLUME, 0o755)
        directory(RELAY_DIR,RELAY,RELAY,0o700)
        for name in ROLES:
            try:
                self.start_node(name,directory,daemon)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.issues[name] = str(error)
        if len(self.procs) == 2:
            self.relay = daemon([sys.executable,'-B',APP/'blockrelay.py'],RELAY,RELAY,'blockrelay')
        directory('/run/radio', RADIO, RADIO, 0o700)
        for port in Path('/sys/class/virtio-ports').glob('*/name'):
            if port.read_text().strip() == 'refugium.radio':
                with open('/dev/'+port.parent.name,'rb',buffering=0) as stream:
                    self.radio = launch([sys.executable,'-B',APP/'radio.py'],RADIO,RADIO,stdin=stream,
                                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                break

    def start_node(self,name,directory,daemon):
        uid, exe, base_conf, _ = ROLES[name]
        run = Path('/run')/name
        directory(run,uid,uid,0o700)
        secret = secrets.token_hex(32)
        salt = secrets.token_hex(16)
        verifier = hmac.new(salt.encode(),secret.encode(),hashlib.sha256).hexdigest()
        key = RELAY_DIR/(name+'.key')
        key.write_text(secret)
        os.chown(key,RELAY,RELAY)
        os.chmod(key,0o400)
        conf = run/'bitcoin.conf'
        conf.write_text((BASE/base_conf).read_text()+'rpcauth=blockrelay:'+salt+'$'+verifier+'\n')
        os.chown(conf,uid,uid)
        data = VOLUME/name
        args = [exe,'-conf='+str(conf)]
        if not data.exists():
            staging = VOLUME/('.initializing-'+name)
            if staging.exists():
                shutil.rmtree(staging)
            directory(staging,uid,uid,0o700)
            init = daemon([*args,'-datadir='+str(staging),'-networkactive=0'],uid,uid,name+'-init')
            try:
                subprocess.run(cli(name,'getblockchaininfo','-rpcwait','-rpcwaittimeout=30'),check=True,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
            finally:
                init.terminate()
                try:
                    init.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    init.kill()
                    init.wait()
                    raise
            if init.returncode:
                raise ValueError('Initial node shutdown failed')
            os.sync()
            staging.rename(data)
            fd = os.open(VOLUME,os.O_RDONLY|os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        directory(data,uid,uid,0o700)
        if name == 'archive':
            args.extend('-connect='+peer for peer in ARCHIVE_PEERS.read_text().splitlines())
        self.procs[name] = daemon([*args,'-datadir='+str(data)],uid,uid,name)

    async def status(self):
        async def info(name):
            proc = self.procs.get(name)
            if not proc or proc.poll() is not None:
                return {'issue':self.issues.get(name,'Node stopped')}
            async def query(method):
                client = await asyncio.create_subprocess_exec(*cli(name,method),
                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                try:
                    data, _ = await asyncio.wait_for(client.communicate(), 3)
                except TimeoutError:
                    client.kill()
                    await client.wait()
                    return None
                return json.loads(data) if client.returncode == 0 else None

            chain, peers = await asyncio.gather(query('getblockchaininfo'),query('getconnectioncount'))
            if chain is None:
                return {'issue':'RPC unavailable'}
            status = {k:chain[k] for k in ('chain','blocks','headers','bestblockhash','pruned')}
            status['peers'] = peers
            return status
        archive, satellite = await asyncio.gather(*(info(name) for name in ROLES))
        state = {'archive':archive,'satellite':satellite,'radio_input':bool(self.radio and self.radio.poll() is None)}
        try:
            age = time.time() - Path('/run/radio/last-datagram').stat().st_mtime
            state['radio_last_datagram_age_seconds'] = max(0,int(age))
        except FileNotFoundError:
            state['radio_last_datagram_age_seconds'] = None
        if self.issues:
            state['issues'] = self.issues
        try:
            state['relay'] = json.loads((RELAY_DIR/'status').read_text())
        except FileNotFoundError:
            pass
        return state

    async def stop(self):
        for p in (self.radio,self.relay):
            if p and p.poll() is None:
                p.terminate()
                await asyncio.to_thread(p.wait)
        for p in self.procs.values():
            if p.poll() is None:
                p.terminate()
        await asyncio.gather(*(asyncio.to_thread(p.wait) for p in self.procs.values()))
        if self.mounted:
            os.sync()
            subprocess.run(['umount',VOLUME],check=True)
