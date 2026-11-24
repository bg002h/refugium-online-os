"""Local explorer processes and read-only credentials on the desktop image."""
import asyncio
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import time

from settings import APP, INDEXER, LOCAL_WEB, MEMPOOL

APPS = Path('/opt/refugium-desktop')
SESSION = APP/'desktop'
INDEX_RUN = Path('/run/electrs')
POOL_RUN = Path('/run/mempool')

# These accounts are never authorized to send transactions or change the node.
INDEX_METHODS = ('getnetworkinfo,getblockchaininfo,getbestblockhash,getblockcount,getblockhash,getblockheader,'
                 'getblock,getrawmempool,getrawtransaction,getmempoolinfo,getmempoolentry,estimatesmartfee,'
                 'getblockstats,gettxout,getindexinfo,getmempoolancestors,getmempooldescendants,getdifficulty')
POOL_METHODS = (INDEX_METHODS + ',getchaintips,getnetworkhashps,getmininginfo,gettxoutsetinfo,'
                'getblocktemplate,decoderawtransaction,validateaddress,getpeerinfo,getmempoolcluster')


def archive_auth(directory):
    lines = []
    for name, uid, run, methods in [('electrs', INDEXER, INDEX_RUN, INDEX_METHODS),
                                     ('mempool', MEMPOOL, POOL_RUN, POOL_METHODS)]:
        directory(run, uid, uid, 0o700)
        secret = secrets.token_hex(32)
        salt = secrets.token_hex(16)
        digest = hmac.new(salt.encode(),secret.encode(),hashlib.sha256).hexdigest()
        cookie = run/'.cookie'
        cookie.write_text(name+':'+secret)
        os.chown(cookie, uid, uid)
        os.chmod(cookie, 0o400)
        lines.extend([f'rpcauth={name}:{salt}${digest}',f'rpcwhitelist={name}:{methods}'])
    return '\n'.join(lines)+'\n'


def indexed_tip():
    conn = http.client.HTTPConnection('127.0.0.1',3000,timeout=.6)
    try:
        conn.request('GET','/blocks/tip/height')
        response = conn.getresponse()
        return int(response.read(32)) if response.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        conn.close()


class Explorers:
    def __init__(self):
        self.children = {}
        self.commands = {}
        self.retry_after = {}

    def start(self, directory, archive_ready):
        web = Path('/run/local-web')
        directory(web, LOCAL_WEB, LOCAL_WEB, 0o700)
        self.commands['web'] = (['/usr/sbin/nginx','-c',str(SESSION/'nginx.conf')], LOCAL_WEB, web, {})
        if archive_ready:
            directory('/mainnet/esplora-index', INDEXER, INDEXER, 0o700)
            directory(POOL_RUN/'cache', MEMPOOL, MEMPOOL, 0o700)
            config = {
                'MEMPOOL': {'BACKEND':'esplora','HTTP_PORT':8999,'CACHE_DIR':str(POOL_RUN/'cache'),
                            'INDEXING_BLOCKS_AMOUNT':0,'AUTOMATIC_POOLS_UPDATE':False,
                            'EXTERNAL_ASSETS':[],'STDOUT_LOG_MIN_PRIORITY':'warn'},
                'ESPLORA': {'REST_API_URL':'http://127.0.0.1:3000'},
                'CORE_RPC': {'HOST':'127.0.0.1','PORT':8332,'COOKIE':True,'COOKIE_PATH':str(POOL_RUN/'.cookie')},
                **{name:{'ENABLED':False} for name in ('DATABASE','STATISTICS','SYSLOG','FIAT_PRICE','LIGHTNING','REDIS','REPLICATION')}
            }
            conf = POOL_RUN/'config.json'
            conf.write_text(json.dumps(config))
            os.chown(conf,MEMPOOL,MEMPOOL)
            self.commands['electrs'] = ([str(APPS/'bin/electrs'),'-v','--network','mainnet',
                '--daemon-dir',str(INDEX_RUN),'--daemon-rpc-addr','127.0.0.1:8332','--jsonrpc-import',
                '--db-dir','/mainnet/esplora-index','--http-addr','127.0.0.1:3000',
                '--electrum-rpc-addr','127.0.0.1:50001','--monitoring-addr','127.0.0.1:4224'],
                INDEXER,INDEX_RUN,{'LD_LIBRARY_PATH':str(APPS/'lib'),'RAYON_NUM_THREADS':'2'})
            self.commands['mempool'] = ([str(APPS/'bin/node'),str(APPS/'backend/index.js')],MEMPOOL,POOL_RUN,
                                        {'MEMPOOL_CONFIG_FILE':str(conf), 'NODE_ENV':'production'})
        self.poll()

    def poll(self):
        for name,(cmd,uid,cwd,env) in self.commands.items():
            log_path = Path('/run/log')/name
            if log_path.exists() and log_path.stat().st_size > 512 * 1024:
                log_path.write_bytes(b'')
            child = self.children.get(name)
            if child is not None and child.poll() is None:
                continue
            if time.monotonic() < self.retry_after.get(name,0):
                continue
            self.retry_after[name] = time.monotonic()+20
            with log_path.open('ab') as log:
                self.children[name] = subprocess.Popen(cmd,user=uid,group=uid,extra_groups=[],cwd=cwd,
                    start_new_session=True,umask=0o077,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(cwd),**env})

    async def stop(self):
        processes = list(self.children.values())
        for child in processes:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
        for child in processes:
            try:
                await asyncio.wait_for(asyncio.to_thread(child.wait), 15)
            except TimeoutError:
                os.killpg(child.pid,signal.SIGKILL)
                await asyncio.to_thread(child.wait)
