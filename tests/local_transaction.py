#!/usr/bin/env python3
"""Use a private regression chain to test real signatures, fees and the HTTPS submission path."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from unittest.mock import patch

from test_services import Explorer, ROOT, explorer


def exercise(bin_dir):
    if {name for _, name in socket.if_nameindex()} != {'lo'}:
        raise RuntimeError('Run this test inside a loopback-only network namespace')
    work = ROOT/'.work/tests'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as td:
        common = ['-regtest', '-datadir='+td, '-rpcport=18219']
        node = subprocess.Popen([bin_dir/'bitcoind', *common, '-networkactive=0', '-listen=0',
                                 '-dnsseed=0', '-printtoconsole=0'], stdout=subprocess.DEVNULL)
        def cli(method, *params, wallet=False):
            prefix = [bin_dir/'bitcoin-cli', *common, '-rpcwait', '-rpcwaittimeout=15']
            if wallet:
                prefix += ['-rpcwallet=fixture']
            return subprocess.check_output([*prefix, method, *params], text=True, timeout=25).strip()
        try:
            cli('createwallet', 'fixture')
            address = cli('getnewaddress', wallet=True)
            cli('generatetoaddress', '101', address)
            raw = cli('createrawtransaction', '[]', json.dumps({address:1}))
            funded = json.loads(cli('fundrawtransaction', raw, json.dumps({'fee_rate':2}), wallet=True))
            signed = json.loads(cli('signrawtransactionwithwallet', funded['hex'], wallet=True))
            assert signed['complete']
            tx = signed['hex']
            production_rpc = explorer.rpc
            def local_rpc(method, *args):
                data = production_rpc(method, *args)
                if method == 'getblockchaininfo':
                    # This private chain can create test funds. Adapt only its network label.
                    info = json.loads(data)
                    assert info['chain'] == 'regtest' and not info['initialblockdownload']
                    info['chain'] = 'signet'
                    return json.dumps(info)
                return data
            Explorer.setUpClass()
            try:
                fixture = Explorer('test_confirmed_post_and_receipt')
                with patch.object(explorer, 'CLI', [bin_dir/'bitcoin-cli', *common]), \
                     patch.object(explorer, 'rpc', side_effect=local_rpc):
                    with fixture.assertRaises(ValueError), patch.object(explorer, 'request') as transport:
                        explorer.submit('0100', '0'*64)
                    transport.assert_not_called()
                    check = explorer.preview(tx)
                    assert check['fee_btc'] > 0 and check['vsize'] > 0
                    with fixture.server(reply=check['txid'].encode()) as seen:
                        assert explorer.submit(tx, check['txid']) == {'accepted_txid':check['txid']}
                    assert seen['sni'] == 'blockstream.info'
                    assert seen['line'] == 'POST /signet/api/tx HTTP/1.1' and seen['body'] == tx.encode()
                assert json.loads(cli('getrawmempool')) == []
                print('PASS: real Core signature and fee validation, exact confirmed HTTPS POST, empty node mempool')
            finally:
                Explorer.tearDownClass()
        finally:
            node.terminate()
            node.wait(timeout=30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin_dir', type=Path, help='directory containing Bitcoin Core binaries')
    exercise(parser.parse_args().bin_dir.resolve())
