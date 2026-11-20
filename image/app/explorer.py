"""Three fixed Esplora operations, with TLS verified end to end through Tor."""
import http.client
import json
import re
import socket
import ssl
import subprocess
import sys

from settings import CLI, EXPLORER_HOST, SITE_SOCKET

HOST = EXPLORER_HOST
BASE = '/signet/api'
MAX_HEX = 800_000
HASH = re.compile(r'[0-9a-f]{64}')


class Blockstream(http.client.HTTPSConnection):
    def __init__(self):
        super().__init__(HOST, timeout=45, context=ssl.create_default_context(
            cafile='/etc/ssl/certs/ca-certificates.crt'))

    def connect(self):
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.settimeout(self.timeout)
        try:
            stream.connect(str(SITE_SOCKET))
            self.sock = self._context.wrap_socket(stream, server_hostname=HOST)
        except BaseException:
            stream.close()
            raise


def request(method, path, body=None):
    connection = Blockstream()
    try:
        connection.request(method, BASE + path, body=body,
                                headers={'Content-Type': 'text/plain'} if body else {})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f'Blockstream returned HTTP {response.status}')
        data = response.read(129)
        if len(data) > 128:
            raise ValueError('Unexpected Blockstream response size')
        return data.decode('ascii').strip()
    finally:
        connection.close()


def rpc(method, *args):
    # -stdin keeps the raw transaction out of process listings. Each argument is one line.
    result = subprocess.run([*CLI, '-stdin', method], input=''.join(a+'\n' for a in args),
                            text=True, capture_output=True, timeout=18)
    if result.returncode:
        raise ValueError(f'Local signet node could not complete {method}')
    return result.stdout.strip()


def compare():
    local = json.loads(rpc('getblockchaininfo'))
    if local['chain'] != 'signet':
        raise ValueError('Local node is on a different network')
    tip = request('GET', '/blocks/tip/height')
    if not re.fullmatch(r'[0-9]{1,9}', tip):
        raise ValueError('Unexpected explorer height')
    height = min(local['blocks'], int(tip))
    local_hash = rpc('getblockhash', str(height))
    remote_hash = request('GET', f'/block-height/{height}')
    if not HASH.fullmatch(remote_hash) or not HASH.fullmatch(local_hash):
        raise ValueError('Unexpected block hash')
    return dict(local_height=local['blocks'], local_headers=local['headers'],
                initial_sync=local['initialblockdownload'], explorer_height=int(tip),
                compared_height=height, same_block=local_hash == remote_hash,
                local_hash=local_hash, explorer_hash=remote_hash)


def preview(raw):
    if not isinstance(raw, str) or not 0 < len(raw) <= MAX_HEX or len(raw) % 2 or not re.fullmatch('[0-9a-fA-F]+', raw):
        raise ValueError('Expected a signed transaction in hexadecimal')
    chain = json.loads(rpc('getblockchaininfo'))
    if chain['chain'] != 'signet' or chain['initialblockdownload'] or chain['blocks'] != chain['headers']:
        raise ValueError('Wait for the local signet node to finish syncing')
    row, = json.loads(rpc('testmempoolaccept', json.dumps([raw])))
    if row.get('allowed') is not True or not HASH.fullmatch(row.get('txid', '')):
        raise ValueError('Local signet node did not accept this transaction')
    return dict(txid=row['txid'], fee_btc=row['fees']['base'], vsize=row['vsize'])


def submit(raw, confirmation):
    checked = preview(raw)
    if not isinstance(confirmation, str) or checked['txid'] != confirmation:
        raise ValueError('Confirm the exact transaction ID')
    try:
        receipt = request('POST', '/tx', raw.encode('ascii'))
        if receipt != confirmation:
            raise ValueError('Unexpected transaction receipt')
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise ValueError('Broadcast outcome unknown. Check the transaction ID before retrying.') from error
    return {'accepted_txid': receipt}


def main():
    try:
        msg = json.load(sys.stdin)
        op = msg['command']
        if op == 'compare':
            data = compare()
        elif op == 'preview':
            data = preview(msg['raw'])
        elif op == 'broadcast':
            data = submit(msg['raw'], msg['confirm'])
        else:
            raise ValueError('Unknown explorer operation')
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, http.client.HTTPException) as e:
        print(json.dumps({'error': str(e)}))
        return 1
    print(json.dumps(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
