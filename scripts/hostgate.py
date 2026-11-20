"""Private host-side lifecycle operations for a single QEMU instance."""
import contextlib
import fcntl
import json
import os
import socket
import time


@contextlib.contextmanager
def exclusive(path):
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def active(state):
    with (state/'instance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


class Monitor:
    def __init__(self, state):
        self.path = state/'monitor.sock'

    def __enter__(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(5)
        try:
            self.sock.connect(str(self.path))
            self.io = self.sock.makefile('rwb', buffering=0)
            if 'QMP' not in json.loads(self.io.readline()):
                raise OSError('Unrecognized machine monitor')
            self.command('qmp_capabilities')
            return self
        except BaseException:
            self.sock.close()
            raise

    def __exit__(self, *_):
        self.io.close()
        self.sock.close()

    def command(self, operation, **arguments):
        self.io.write(json.dumps({'execute':operation,'arguments':arguments}).encode()+b'\n')
        while True:
            reply = json.loads(self.io.readline())
            if 'error' in reply:
                raise RuntimeError(reply['error']['desc'])
            if 'return' in reply:
                return reply['return']

    def has_backend(self):
        return any('type=user' in line for line in self.backends().splitlines())

    def backends(self):
        return self.command('human-monitor-command', **{'command-line':'info network'})


def wait_monitor(state, process):
    end = time.monotonic()+20
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError('QEMU exited at startup')
        try:
            with Monitor(state):
                return
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(.1)
    raise TimeoutError('Machine monitor did not start')


def flush_dir(state):
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def monitor_live(state):
    try:
        with Monitor(state):
            return True
    except (ConnectionRefusedError, FileNotFoundError):
        return False


def seal(state):
    marker = state/'sealed'
    with marker.open('a') as out:
        os.fsync(out.fileno())
    flush_dir(state)
    if active(state) or monitor_live(state):
        with Monitor(state) as monitor:
            try:
                monitor.command('netdev_del', id='u')
            except RuntimeError as error:
                if str(error) != "Device 'u' not found":
                    raise
            if 'wan: index=' in monitor.backends():
                # The backend has already been removed. Give the guest a carrier-change signal too.
                monitor.command('set_link', name='wan', up=False)
            if monitor.has_backend():
                raise RuntimeError('Running uplink removal unconfirmed')
    return 'Sealed. The running uplink is absent. Future boots have no adapter.'


def arm(state):
    if active(state) or monitor_live(state):
        raise RuntimeError('Power off this instance before arming a future boot')
    (state/'sealed').unlink(missing_ok=True)
    flush_dir(state)
    return 'Armed for a future boot. The guest will start with outbound traffic locked.'
