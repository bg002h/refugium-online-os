"""Copy missing main-chain blocks over two narrowly authorized local RPC connections."""
import base64
import http.client
import json
import os
from pathlib import Path
import time


class RpcError(Exception):
    pass


class Rpc:
    def __init__(self, port, credential):
        self.port = port
        self.auth = 'Basic ' + base64.b64encode(credential.encode()).decode()

    def __call__(self, method, *params):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=90)
        try:
            body = json.dumps({'id':1, 'method':method, 'params':params})
            conn.request('POST','/',body,{'Authorization':self.auth,'Content-Type':'application/json'})
            result = json.loads(conn.getresponse().read())
            if result['error']:
                raise RpcError(result['error']['message'])
            return result['result']
        finally:
            conn.close()


def transfer(source, archive, cursor=None, batch=32):
    src = source('getblockchaininfo')
    dst = archive('getblockchaininfo')
    if src['chain'] != 'main' or dst['chain'] != 'main' or not src['pruned'] or dst['pruned']:
        raise ValueError('Expected pruned mainnet receiver and unpruned mainnet archive')
    if int(src['chainwork'],16) <= int(dst['chainwork'],16):
        return None, {'state':'no new receiver work','receiver_height':src['blocks']}
    if cursor and cursor[0] <= src['blocks'] and source('getblockhash',cursor[0]) == cursor[1]:
        height = cursor[0]
    else:
        # Find the shared ancestor, including when Tor and the receiver see different tips.
        lo,hi = 0,min(src['blocks'],dst['blocks'])
        while lo < hi:
            mid = (lo+hi+1)//2
            if source('getblockhash',mid) == archive('getblockhash',mid):
                lo = mid
            else:
                hi = mid-1
        height = lo
    if height+1 < src.get('pruneheight',0):
        return None, {'state':'receiver has pruned the next required block',
                      'required_height':height+1,'oldest_available':src['pruneheight']}
    for number in range(height+1,min(height+batch,src['blocks'])+1):
        blockhash = source('getblockhash',number)
        raw = source('getblock',blockhash,0)
        rejection = archive('submitblock',raw)
        if rejection not in (None,'duplicate'):
            raise RpcError('Archive rejected block: '+str(rejection))
        cursor = number,blockhash
    return cursor, {'state':'copied blocks','through':cursor[0]} if cursor else {'state':'waiting'}


def main():
    from satellite_roles import RELAY_DIR
    src, dst = [Rpc(port,'blockrelay:'+ (RELAY_DIR/name).read_text().strip())
                for port,name in [(8432,'satellite.key'),(8332,'archive.key')]]
    cursor = None
    last = None
    while True:
        try:
            cursor, state = transfer(src,dst,cursor)
        except (OSError, RpcError, ValueError, KeyError, http.client.HTTPException) as error:
            cursor, state = None, {'state':'receiver or archive unavailable','detail':str(error)[:180]}
        if state != last:
            pending = RELAY_DIR/'status.new'
            pending.write_text(json.dumps(state))
            os.replace(pending, RELAY_DIR/'status')
            last = state
        if state['state'] != 'copied blocks':
            time.sleep(3)


if __name__ == '__main__':
    main()
