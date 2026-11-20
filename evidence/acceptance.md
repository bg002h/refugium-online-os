# Signet VM acceptance

On November 20, 2026 UTC, the x86-64 UEFI disk booted under QEMU 11.1.2 with OVMF and KVM. It ran Ubuntu Noble userspace, Linux 6.12.118, Bitcoin Core 31.1, Tor 0.4.9.11 and nftables 1.0.9.

Two clean kernel builds and two assemblies, using independently fetched pinned inputs, produced identical boot disks on this toolchain. The unsigned disk is 97,534,464 bytes. Its digest is in [SHA256SUMS](SHA256SUMS). The kernel SHA-256 was `9d55d88cd343eda024d7e2341dcb3697ae6ad6f141c34eb7b04825fac759e87b`. The Ubuntu snapshot supplied all 50 locked packages. Two signatures on the Bitcoin Core checksum manifest verified with signing fingerprints `152812300785C96444D3334D17565732E08E5E41` and `CFB16E21C950F67FA95E558F2EEB9F5CC09526C1`.

## Wire results

An independent QEMU capture recorded Ethernet frames at the host’s network backend. The guest had its normal virtual adapter. Each cutoff observation below lasted ten seconds. A comparison request was queued alongside the guest cutoff. A packet already in transit toward the guest can still arrive at the host capture after the guest has cut its own link.

| Point in the booted distribution image | Guest frames sent | Frames received at the host capture |
| --- | ---: | ---: |
| Before the first operator connect | 0 | 0 |
| Guest acknowledged `lock` | 237 | 352 |
| Ten seconds later | 237 | 359 |
| Host removed backend after a second Tor connection | 482 | 693 |
| Ten seconds later | 482 | 693 |

Across that session, 480 outbound frames were IPv4 TCP to public port 443 and two were local gateway ARP. The host monitor confirmed backend removal. The running VM refused re-arming, the guest refused reconnection, and a persistent sealed boot had no adapter or backend. Starting with `--sealed` also omitted both. Local signet RPC continued to work. Re-arming a powered-off sealed instance allowed an adapter on the next boot, which emitted zero frames before `connect`. In a separate test, killing the launcher left the instance lock in QEMU. The host could still enforce a seal.

The public test reached Tor bootstrap 100%. Core and Blockstream independently supplied the same signet hash at height **331656**, `00000011a81c31adb58e12718ebb0a9d009da892e9be8404a8f6c54fe0458f12`. The tip test started from a disposable copy of public chain data. A second run with an empty data disk reached six peers and 14,276 headers before it was stopped. Its common-height comparison correctly reported genesis at the time of comparison and flagged initial block download.

## Boot and power interruptions

A first-boot power cut in an intermediate build left Core's new block-obfuscation file empty. The final supervisor initializes a fresh chain with networking locked, stops Core cleanly, flushes the disk, and publishes the initialized directory in one rename before normal operation. Repeating the cut during live Tor traffic recovered local signet RPC and sent zero frames on restart. An intentionally unfinished staging directory recovered on a sealed boot. An already damaged published data directory stayed locked and reported the local node failure. Two presented adapters triggered an explicit refusal, and captures on both recorded zero frames.

## Policy and transactions

A separate test loaded the distribution kernel and root filesystem with a disposable test init under restricted QEMU networking. It attempted external TCP 443, TCP 80 and UDP 53 for six UIDs with the guest firewall locked, enabled and relocked. Only the Tor UID emitted external IP frames, exclusively on TCP 443 in the enabled phase. Both general Tor listeners were inaccessible to the explorer, Core and console UIDs. The kernel rejected IPv6 and packet sockets. The shipped boot image contains the ordinary supervisor.

The six protocol tests checked the peer and port allowlist, fixed Blockstream tunnel destination, end-to-end TLS, certificate and redirect rejection, mismatched block hashes, exact transaction confirmation and ambiguous receipts. An additional test mined spendable funds on an isolated regression chain, signed a transaction and ran the real Core mempool check. A local HTTPS fixture received the exact confirmed bytes at `/signet/api/tx`. Invalid input stopped before HTTP, and the node’s mempool stayed empty. Only the network label was adapted for this local regression-chain test. The public signet test used read-only explorer requests. No public transaction was sent.

In the packaged RPC policy, local chain and connection queries succeeded. An unlisted RPC method returned HTTP 403. The cookie permits only `getblockchaininfo`, `getblockhash`, `getconnectioncount` and `testmempoolaccept`.

## Repeating the checks

Use a dedicated state directory. The host-cutoff tests deliberately power it off and leave its latch sealed. Run `scripts/run IMAGE STATE --serial-socket SOCKET --capture CAPTURE`, then `python3 -B tests/vm_session.py SOCKET CAPTURE STATE` in another terminal. For a synchronized test disk, add `--synced`; the test then requires matching hashes up to the explorer tip. Run `tests/isolated-network IMAGE NEW_DIRECTORY` for the restricted packet matrix. Use `python3 -B tests/launcher_exit.py IMAGE NEW_DIRECTORY` for launcher loss. The commands `python3 -B tests/power_loss.py IMAGE NEW_DIRECTORY` and `python3 -B tests/extra_interface.py IMAGE NEW_DIRECTORY` repeat the abrupt reboot and extra-adapter checks.

The local transaction check requires Bitcoin Core 31.1, OpenSSL and a loopback-only network namespace. Point the argument at the built image’s directory containing the two Core executables.

```sh
unshare --user --map-root-user --net sh -ec 'ip link set lo up; exec python3 -B tests/local_transaction.py "$1"' sh PATH_TO_CORE_BIN
```

The boot media is unsigned. These observations qualify the listed VM configuration and sample windows. Physical networking, a full public sync from genesis to tip, and public broadcast remain outside the measured results.
