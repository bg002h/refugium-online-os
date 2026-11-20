# Mainnet receiver and archive acceptance

On November 20, 2026 UTC the x86-64 QEMU/KVM image ran Bitcoin Core 31.1 on mainnet and signet and Bitcoin Satellite v25.0-satellite0.2.4 on mainnet. All wallets were disabled. The receiver’s prune target was 2048 MiB. The archive had pruning disabled.

| Check | Observed |
| --- | --- |
| Sealed cold boot | QEMU reported no network adapter or user network backend. Guest `connect` was refused. All three nodes started at genesis. |
| Host receiver to archive | A local Blockstream transmitter fixture supplied real mainnet blocks 1–3 over IPv4 multicast. The host adapter, serial port, guest multicast receiver and authenticated block relay were all on the path. Both mainnet nodes reached block 3 with hash `0000000082b5015589a3fdf2d4baff403e6f0be035a5d9742c1cae6295464449`. Signet remained at genesis. Neither mainnet node had an Internet peer. |
| Sealed reboot | Both mainnet nodes retained block 3. The radio activity field returned to null before any new input. |
| Firewall | Probes exercised 10 identities across locked, Tor-enabled and relocked states. The external capture showed only the Tor identity sending external IPv4 frames, all TCP to port 443. IPv6 and raw packet sockets remained unavailable. |
| Both chains over Tor | After operator activation Tor bootstrapped to 100%. The archive had one mainnet peer, signet had five peers and the satellite node had zero peers. After the guest lock the outbound packet count stayed at 2,303 over five seconds (one gateway ARP and 2,302 Tor TCP/443 frames). The host seal then refused reconnection. |
| Missing signet disk | With the signet volume absent, both mainnet nodes started and the operator could enable and lock Tor for the archive. |
| Relay edge cases | RPC tests exercised a higher-work fork, partial batch and resume, missing pruned history, a receiver behind its archive, an archive rejection and a network mismatch. |

The test used two 8 GiB scratch disks and exercised initial block transfer. It did not synchronize a full mainnet archive or measure live RF reception. A receiver that has already discarded necessary historical blocks cannot supply them to a newly started archive.

## Replaying the sealed test

Start the image with a new test state directory. Use the serial socket and run the test from a second host terminal. The test powers the VM off on success.

```sh
scripts/run .work/refugium-online-os.img .work/radio-test --sealed --mainnet-size-gib 8 --serial-socket .work/radio.sock
python3 -B tests/satellite_vm.py .work/radio.sock .work/radio-test
```

Boot the same state again with the same command. From the second terminal, run `python3 -B tests/satellite_vm.py --persisted .work/radio.sock .work/radio-test`. The host test uses bubblewrap with an isolated loopback network. It needs no dish, public peer or website.

The datagram fixture was produced by Blockstream’s Noble v0.2.4 transmitter using public raw blocks 1, 2 and 3, a repeat depth of three and interleave length of one. The gzip file contains 160 distinct length-prefixed FIBRE datagrams. The test checks the input header hashes against mainnet genesis and the expected block-3 hash. [Blockstream transmitter source](https://github.com/Blockstream/bitcoinsatellite/tree/v25.0-satellite0.2.4) · [Block 3](https://blockstream.info/block/0000000082b5015589a3fdf2d4baff403e6f0be035a5d9742c1cae6295464449)

## Build and availability

The unmodified Noble receiver attempts to open a dual-stack socket for IPv4 multicast. On the appliance kernel it exited during UDP initialization. The shipped receiver builds from the pinned upstream tag with a small IPv4 multicast socket patch. The common UDP read path accepts the actual sender address family and length. The Tor and signet firewall rules continue to run on an IPv4-only kernel. [Upstream socket code](https://github.com/Blockstream/bitcoinsatellite/blob/v25.0-satellite0.2.4/src/udpnet.cpp) · [Appliance patch](../image/satellite/ipv4-multicast.patch)

| Artifact | SHA-256 |
| --- | --- |
| Boot image | `5d93f649d3f0f9d4c5e5e2e987ff146e17ed814285392643ffdaf1c5e8849c54` |
| Bitcoin Satellite executable | `f85d067d619ee858643c29639bf526c0ac63931bccd85069f521051b450cd9c9` |
| Kernel | `22ddffae83070107d599b3c18b83712b7f66b48e454c9ea380ad722f00fd5d0d` |

Checked November 20, 2026. The official public Satellite API listed message 34639 as received with a November 17 transmission end time and 34688 as sent on November 18. This is evidence about the messaging service. Current regional Bitcoin block reception requires separate observation. Blockstream’s changelog records the 2024 Eutelsat 113 decommissioning and a May 2026 Galaxy 18 frequency update. [API received queue](https://api.blockstream.space/orders/received?channel=1&limit=5) · [API sent queue](https://api.blockstream.space/orders/sent?channel=1&limit=5) · [Release changelog](https://github.com/Blockstream/satellite/blob/v2.5.2/CHANGELOG.md)
