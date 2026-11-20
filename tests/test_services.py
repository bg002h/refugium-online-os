"""Local protocol checks. All explorer POSTs in this suite terminate at a loopback fixture."""
import asyncio
import contextlib
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'image/app'))
import explorer
import peer_filter


class Sink:
    def __init__(self):
        self.written = bytearray()

    def write(self, data):
        self.written.extend(data)

    async def drain(self):
        pass


class Filters(unittest.IsolatedAsyncioTestCase):
    async def negotiate(self, name, port=38333, command=1):
        peers = set((ROOT/'image/peers').read_text().splitlines())
        raw = name.encode()
        reader = asyncio.StreamReader()
        reader.feed_data(b'\x05\x01\0' + bytes([5,command,0,3,len(raw)]) + raw + port.to_bytes(2,'big'))
        reader.feed_eof()
        return await peer_filter.handshake(reader, Sink(), peers)

    async def test_only_exact_peer_and_port(self):
        name = (ROOT/'image/peers').read_text().splitlines()[0].split(':')[0]
        self.assertEqual(await self.negotiate(name), (name.encode(),38333))
        for dest, port, cmd in [(name,443,1),('blockstream.info',443,1),(name+'.example',38333,1),
                                ('127.0.0.1',38333,1),(name,38333,2),(name,38333,3)]:
            with self.subTest(dest=dest, port=port, cmd=cmd), self.assertRaises(ValueError):
                await self.negotiate(dest,port,cmd)


    async def test_fixed_web_tunnel_selects_origin_without_reading_client_destination(self):
        # A web client supplies TLS bytes. Destination selection must already be complete.
        class Local(Sink):
            def get_extra_info(self, name):
                return self
            def getsockopt(self, *args):
                import struct
                return struct.pack('3i', 1, peer_filter.WEB, 123)
            def close(self):
                pass
        async def stop(name, port, listener):
            self.assertEqual((name,port,listener),(b'blockstream.info',443,9051))
            raise ValueError('fixture ends before opening a circuit')
        with patch.object(peer_filter,'open_tor_stream',side_effect=stop) as upstream:
            await peer_filter.serve(asyncio.StreamReader(),Local())
            upstream.assert_awaited_once()


class Explorer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=ROOT/'.work/tests'
        directory.mkdir(parents=True, exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=directory)
        cls.cert=Path(cls.temp.name)/'tls.crt'
        cls.key=Path(cls.temp.name)/'tls.key'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=blockstream.info','-addext','subjectAltName=DNS:blockstream.info',
                        '-out',cls.cert,'-keyout',cls.key],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @contextlib.contextmanager
    def server(self, response=b'200 OK', reply=b'12', trust=True):
        path=Path(self.temp.name)/'site.sock'
        path.unlink(missing_ok=True)
        listener=socket.socket(socket.AF_UNIX)
        listener.bind(str(path))
        listener.listen(1)
        listener.settimeout(5)
        recorded={}
        client=ssl.create_default_context(cafile=str(self.cert)) if trust else ssl.create_default_context()
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(self.cert,self.key)
        tls.set_servername_callback(lambda _, name, __: recorded.update(sni=name))
        def run_server():
            try:
                with listener, listener.accept()[0] as sock:
                    with tls.wrap_socket(sock,server_side=True) as enc, enc.makefile('rb') as f:
                        recorded['line']=f.readline().decode().strip()
                        headers={}
                        while (line:=f.readline()) not in (b'\r\n',b''):
                            k,v=line.decode().split(':',1); headers[k.lower()]=v.strip()
                        recorded['body']=f.read(int(headers.get('content-length','0')))
                        enc.sendall(b'HTTP/1.1 '+response+b'\r\nLocation: https://other.invalid/\r\nContent-Length: '+
                                    str(len(reply)).encode()+b'\r\nConnection: close\r\n\r\n'+reply)
            except ssl.SSLError as e:
                if trust: recorded['error']=str(e)
            except Exception as e:
                recorded['error']=str(e)
        th=threading.Thread(target=run_server,daemon=True); th.start()
        with patch.object(explorer,'SITE_SOCKET',path), \
             patch.object(explorer.ssl,'create_default_context',return_value=client):
            try: yield recorded
            finally:
                th.join(6)
                self.assertFalse(th.is_alive())
                self.assertNotIn('error',recorded)

    def test_get_via_private_socket_and_tls(self):
        with self.server() as seen:
            self.assertEqual(explorer.request('GET','/blocks/tip/height'),'12')
        self.assertEqual(seen['sni'],'blockstream.info')
        self.assertEqual(seen['line'],'GET /signet/api/blocks/tip/height HTTP/1.1')

    def test_refuse_redirect_and_bad_tls(self):
        with self.server(response=b'302 Found'), self.assertRaisesRegex(ValueError,'302'):
            explorer.request('GET','/blocks/tip/height')
        with self.server(trust=False), self.assertRaises(ssl.SSLCertVerificationError):
            explorer.request('GET','/blocks/tip/height')

    def test_confirmed_post_and_receipt(self):
        txid='a'*64
        chain={'chain':'signet','initialblockdownload':False,'blocks':12,'headers':12}
        row=[{'allowed':True,'txid':txid,'vsize':120,'fees':{'base':0.0001}}]
        replies={'getblockchaininfo':json.dumps(chain),'testmempoolaccept':json.dumps(row)}
        with patch.object(explorer,'rpc',side_effect=lambda method,*args: replies[method]):
            with patch.object(explorer,'request') as http:
                with self.assertRaises(ValueError):
                    explorer.submit('0100','b'*64)
                http.assert_not_called()
            with self.server(reply=txid.encode()) as seen:
                self.assertEqual(explorer.submit('0100',txid),{'accepted_txid':txid})
            self.assertEqual(seen['line'],'POST /signet/api/tx HTTP/1.1')
            self.assertEqual(seen['body'],b'0100')
            with self.server(reply=b'wrong'), self.assertRaisesRegex(ValueError,'unknown'):
                explorer.submit('0100',txid)
            chain['initialblockdownload']=True
            replies['getblockchaininfo']=json.dumps(chain)
            with patch.object(explorer,'request') as http:
                with self.assertRaisesRegex(ValueError,'sync'):
                    explorer.submit('0100',txid)
                http.assert_not_called()

    def test_common_height_and_different_hash(self):
        def rpc(method,*args):
            if method=='getblockchaininfo':
                return json.dumps(dict(chain='signet',blocks=7,headers=12,initialblockdownload=True))
            self.assertEqual((method,args),('getblockhash',('7',)))
            return 'a'*64
        with patch.object(explorer,'rpc',side_effect=rpc), patch.object(explorer,'request',side_effect=['12','b'*64]) as req:
            result=explorer.compare()
        self.assertEqual((result['same_block'],result['compared_height'],result['explorer_height']),(False,7,12))
        self.assertEqual(req.call_args.args,('GET','/block-height/7'))


if __name__=='__main__':
    unittest.main(verbosity=2)
