"""PID 1 for the single-uplink Bitcoin appliance."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import struct
import subprocess
import sys
import time

from satellite_roles import Mainnet
import firewall
from settings import APP, ARCHIVE, BITCOIN, CLI, CONTROL, FILTER, OPERATOR, PEERS, TOR, WEB


def run(*args, **options):
    return subprocess.run(args, check=True, stdin=subprocess.DEVNULL, **options)


def directory(path, uid, gid, mode):
    if Path(path).is_symlink():
        raise ValueError("Unexpected link in appliance directory")
    Path(path).mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def launch(argv, uid, gid, groups=(), **options):
    return subprocess.Popen(argv, user=uid, group=gid, extra_groups=groups,
                            start_new_session=True, umask=0o077, close_fds=True,
                            env={'PATH': '/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                                 'HOME': '/', 'LANG': 'C', 'PYTHONDONTWRITEBYTECODE': '1'},
                            **options)


def kill_group(proc):
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)


class Appliance:
    def __init__(self):
        self.interface = None
        self.mode = 'locked'
        self.issue = ''
        self.node = self.tor = self.broker = None
        self.workers = set()
        self.consoles = []
        self.stopping = False
        self.cutoff_error = None
        self.tor_data = None
        self.mount = False
        self.mainnet = Mainnet()

    def boot(self):
        external = sorted(p.name for p in Path('/sys/class/net').iterdir() if p.name != 'lo')
        for device in external:
            run('ip', 'link', 'set', 'dev', device, 'down')
        if len(external) == 1:
            self.interface = external[0]
        firewall.install(self.interface, False)
        run('ip', 'link', 'set', 'lo', 'up')
        run('ip', 'route', 'replace', '239.0.0.2/32', 'dev', 'lo', 'src', '127.0.0.1')
        if len(external) > 1:
            self.issue = 'Multiple adapters present; network activation disabled'
        if Path('/proc/net/if_inet6').exists():
            raise RuntimeError('Unexpected IPv6 support')
        directory('/run/refugium', 0, OPERATOR, 0o750)
        directory('/run/peer-filter', FILTER, BITCOIN, 0o750)
        directory('/run/main-peer', FILTER, ARCHIVE, 0o2750)
        directory('/run/site-filter', FILTER, WEB, 0o2750)
        directory('/run/bitcoin', BITCOIN, BITCOIN, 0o750)
        directory('/run/bitcoin-client', 0, 0, 0o755)
        directory('/run/bitcoin-client/signet', 0, 0, 0o755)
        Path('/run/log').mkdir(exist_ok=True)
        try:
            self.mainnet.start(directory,self.daemon,launch)
        except (OSError, subprocess.SubprocessError) as error:
            self.mainnet.issues['startup'] = str(error)
        for _ in range(30):
            devices = subprocess.run(['blkid','-t','LABEL=RO_SIGNET','-o','device'],
                                     capture_output=True, text=True).stdout.splitlines()
            if devices:
                break
            time.sleep(.1)
        if len(devices) != 1:
            if self.mainnet.mounted:
                directory('/mainnet/tor', TOR, TOR, 0o700)
                self.tor_data = '/mainnet/tor'
            self.issue = 'One RO_SIGNET data disk is required'
            return
        run('mount', '-t', 'ext4', '-o', 'nodev,nosuid,noexec,noatime', devices[0], '/data')
        self.mount = True
        os.chown('/data', 0, 0)
        os.chmod('/data', 0o755)
        directory('/data/tor', TOR, TOR, 0o700)
        self.tor_data = '/data/tor'
        try:
            self.initialize_chain()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.issue = 'Could not initialize local signet storage: ' + str(error)
            return
        directory('/data/bitcoin', BITCOIN, BITCOIN, 0o700)
        argv = ['/usr/local/bin/bitcoind', '-datadir=/data/bitcoin', '-conf=/etc/refugium-online/bitcoin.conf']
        argv.extend('-connect='+p for p in PEERS.read_text().splitlines())
        self.node = self.daemon(argv, BITCOIN, BITCOIN, 'core')

    def initialize_chain(self):
        final = Path('/data/bitcoin')
        if final.exists():
            return
        # A power cut may interrupt Core's first file creations. Publish a cleanly
        # stopped genesis database in one rename before the normal node can connect.
        staging = Path('/data/.refugium-initializing')
        if staging.is_symlink():
            raise ValueError('Invalid signet initialization directory')
        if staging.exists():
            shutil.rmtree(staging)
        directory(staging, BITCOIN, BITCOIN, 0o700)
        proc = self.daemon(['/usr/local/bin/bitcoind', '-datadir='+str(staging),
                            '-conf=/etc/refugium-online/bitcoin.conf', '-networkactive=0'],
                           BITCOIN, BITCOIN, 'initialize')
        try:
            run(*CLI, '-rpcwait', '-rpcwaittimeout=45', 'getblockchaininfo',
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=50)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=40)
            except subprocess.TimeoutExpired:
                kill_group(proc)
                raise
        if proc.returncode != 0:
            raise ValueError('Initial Core shutdown failed')
        os.sync()
        staging.rename(final)
        fd = os.open('/data', os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def daemon(args, uid, gid, name):
        with open('/run/log/'+name, 'wb') as log:
            return launch(args, uid, gid, stdin=subprocess.DEVNULL, stdout=log, stderr=log)

    def lock(self):
        # Close the packet path before terminating existing streams or reporting success.
        failures = []
        try:
            firewall.install(self.interface, False)
        except (OSError, subprocess.SubprocessError):
            failures.append('firewall')
        if self.interface:
            try:
                run('ip', 'link', 'set', 'dev', self.interface, 'down')
            except (OSError, subprocess.SubprocessError):
                failures.append('link')
        self.mode = 'locked'
        for proc in [*self.workers, self.broker, self.tor]:
            kill_group(proc)
        self.tor = self.broker = None
        if failures:
            self.issue = 'Cutoff control failure: ' + ', '.join(failures)
            self.cutoff_error = self.issue
            raise RuntimeError(self.issue)
        return {'mode': self.mode}

    def has_core(self):
        nodes = (self.node, self.mainnet.procs.get('archive'))
        return any(node is not None and node.poll() is None for node in nodes)

    def connect(self):
        if self.mode == 'tor':
            return {'mode': 'tor'}
        if self.cutoff_error:
            raise ValueError(self.cutoff_error)
        if not self.interface:
            raise ValueError(self.issue or 'No uplink adapter. This boot is sealed.')
        if not self.tor_data or not self.has_core():
            raise ValueError(self.issue or 'Local Core nodes unavailable')
        try:
            run('ip', 'addr', 'replace', '10.0.2.15/24', 'dev', self.interface)
            firewall.install(self.interface, True)
            run('ip', 'link', 'set', 'dev', self.interface, 'up')
            carrier = Path('/sys/class/net', self.interface, 'carrier')
            for _ in range(10):
                if carrier.read_text().strip() == '1':
                    break
                time.sleep(.05)
            else:
                raise ValueError('The host uplink is disconnected')
            run('ip', 'route', 'replace', 'default', 'via', '10.0.2.2', 'dev', self.interface)
            self.tor = self.daemon(['/usr/bin/tor', '-f', '/etc/refugium-online/torrc',
                                    '--DataDirectory', self.tor_data], TOR, TOR, 'tor')
            self.broker = self.daemon([sys.executable, '-B', APP/'peer_filter.py'], FILTER, BITCOIN, 'peers')
            self.mode = 'tor'
            return {'mode': 'tor', 'transport': 'bootstrapping; no direct fallback'}
        except BaseException:
            self.lock()
            raise

    async def status(self):
        status = {'mode': self.mode, 'uplink': self.interface, 'issue': self.issue}
        if self.interface:
            status['link_up'] = bool(int(Path('/sys/class/net', self.interface, 'flags').read_text(),16) & 1)
        if self.tor:
            with open('/run/log/tor', 'rb') as log:
                log.seek(max(0, os.fstat(log.fileno()).st_size - 16384))
                stages = [s.decode(errors='replace').strip().split('Bootstrapped ',1)[1].split(' (',1)[0]
                          for s in log if b'Bootstrapped ' in s]
            status['tor_bootstrap'] = stages[-1] if stages else 'starting'
        if self.node and self.node.poll() is not None:
            status['issue'] = f'Local signet node stopped (exit {self.node.returncode}). Check its data disk.'
        if self.node and self.node.poll() is None:
            for method, key in [('getblockchaininfo','node'),('getconnectioncount','peers')]:
                proc = await asyncio.create_subprocess_exec(*CLI, method, stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.DEVNULL)
                try:
                    raw,_ = await asyncio.wait_for(proc.communicate(), 4)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    break
                if proc.returncode == 0:
                    data = json.loads(raw)
                    status[key] = ({k:data[k] for k in ('chain','blocks','headers','initialblockdownload')}
                                   if key=='node' else data)
        status['mainnet'] = await self.mainnet.status()
        return status

    async def explorer(self, msg):
        if msg['command'] != 'preview' and self.mode != 'tor':
            raise ValueError('Outbound traffic is locked')
        if len(self.workers) >= 4:
            raise ValueError('Explorer is busy')
        proc = launch([sys.executable,'-B',APP/'explorer.py'], WEB, WEB, [BITCOIN],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.workers.add(proc)
        try:
            data,_ = await asyncio.to_thread(proc.communicate, json.dumps(msg).encode(), 140)
            if not data:
                raise ValueError('Operation interrupted; check the transaction ID before retrying a broadcast')
            return json.loads(data)
        finally:
            kill_group(proc)
            self.workers.discard(proc)

    async def handle(self, reader, writer):
        try:
            creds = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i',creds)[1] not in (0,OPERATOR):
                raise ValueError('Console access required')
            msg = json.loads(await asyncio.wait_for(reader.readline(), 5))
            op = msg['command']
            if op == 'lock':
                result = self.lock()
            elif op == 'connect':
                result = self.connect()
            elif op == 'status':
                result = await self.status()
            elif op in ('compare','preview','broadcast'):
                result = await self.explorer(msg)
            elif op == 'poweroff':
                self.lock()
                self.stopping = True
                result = {'mode':'shutting down'}
            else:
                raise ValueError('Unknown command')
        except (ValueError, TypeError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            result = {'error':str(error)}
        try:
            writer.write(json.dumps(result).encode()+b'\n')
            await writer.drain()
        finally:
            writer.close()

    async def start(self):
        self.boot()
        server = await asyncio.start_unix_server(self.handle, CONTROL, limit=850_000)
        os.chown(CONTROL, 0, OPERATOR)
        os.chmod(CONTROL, 0o660)
        for name in ('tty1','ttyS0'):
            try:
                tty = os.open('/dev/'+name, os.O_RDWR|os.O_NOCTTY)
            except OSError:
                continue
            try:
                # Unsigned transactions may be long. The menu accepts multiple lines.
                self.consoles.append(launch([sys.executable,'-B',APP/'console.py'],OPERATOR,OPERATOR,
                                            stdin=tty,stdout=tty,stderr=tty))
            finally:
                os.close(tty)
        while not self.stopping:
            await asyncio.sleep(.5)
            if self.mode == 'tor':
                carrier = Path('/sys/class/net', self.interface, 'carrier').read_text().strip()
                if carrier != '1' or not self.has_core() or any(p.poll() is not None for p in (self.tor,self.broker)):
                    self.lock()
        server.close()
        await server.wait_closed()
        if self.node and self.node.poll() is None:
            self.node.terminate()
            await asyncio.to_thread(self.node.wait)
        await self.mainnet.stop()
        os.sync()
        if self.mount:
            run('umount','/data')
        ctypes.CDLL(None).reboot(0x4321FEDC)


if __name__ == '__main__':
    if os.getpid() != 1 or not Path('/etc/refugium-online/bitcoin.conf').is_file():
        sys.exit('Run only as the booted appliance init')
    ctypes.CDLL(None).prctl(38, 1, 0, 0, 0)  # PR_SET_NO_NEW_PRIVS
    try:
        asyncio.run(Appliance().start())
    except Exception as error:
        print('Appliance startup or shutdown failed:', error, file=sys.stderr, flush=True)
        # The network must stay down on a fatal supervisor error.
        for dev in Path('/sys/class/net').iterdir():
            if dev.name != 'lo':
                subprocess.run(['ip','link','set','dev',dev.name,'down'], check=False)
        while True:
            signal.pause()
