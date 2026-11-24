"""Exercise divergent, fast-forward and pruned mainnet chains with local RPC doubles."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'image/app'))
from blockrelay import RpcError, transfer


class Node:
    def __init__(self, chain, pruned=False, pruneheight=0):
        self.blocks = list(chain)
        self.pruned = pruned
        self.pruneheight = pruneheight
        self.submitted = []
        self.network = 'main'
        self.reject = None

    def __call__(self, method, *args):
        if method == 'getblockchaininfo':
            return dict(blocks=len(self.blocks)-1, chainwork=hex(len(self.blocks)), chain=self.network,
                        pruned=self.pruned, pruneheight=self.pruneheight)
        if method == 'getblockhash':
            return self.blocks[args[0]]
        if method == 'getblock':
            block, verbosity = args
            assert verbosity == 0 and self.blocks.index(block) >= self.pruneheight
            return 'raw-'+block
        if method == 'submitblock':
            self.submitted.append(args[0])
            return self.reject
        raise AssertionError(method)


class Relay(unittest.TestCase):
    def test_competing_branch_resumes_before_it_becomes_best(self):
        sat = Node('012abc', True)
        archive = Node('012xy')
        cursor, _ = transfer(sat, archive, batch=2)
        self.assertEqual(cursor, (4, 'b'))
        end, _ = transfer(sat, archive, cursor)
        self.assertEqual(end, (5, 'c'))
        self.assertEqual(archive.submitted, ['raw-a', 'raw-b', 'raw-c'])

    def test_pruning_gap_and_restored_archive(self):
        sat, archive = Node('012345', True, 3), Node('01')
        cursor, state = transfer(sat, archive)
        self.assertEqual(state['required_height'], 2)
        self.assertEqual(archive.submitted, [])
        archive.blocks.append('2')
        _, state = transfer(sat, archive, cursor)
        self.assertEqual(state['through'],5)
        self.assertEqual(archive.submitted, ['raw-3','raw-4','raw-5'])

    def test_same_or_more_work(self):
        sat, archive = Node('01', True), Node('012')
        transfer(sat, archive)
        self.assertEqual(archive.submitted, [])

    def test_rejection_and_network_mismatch(self):
        sat, archive = Node('012', True), Node('0')
        archive.reject = 'bad-block'
        with self.assertRaises(RpcError): transfer(sat, archive)
        sat.network = 'signet'
        with self.assertRaises(ValueError): transfer(sat, archive)


if __name__ == '__main__':
    unittest.main()
