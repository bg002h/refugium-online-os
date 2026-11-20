# Refugium Online OS

Run a wallet-disabled Bitcoin Core node on public signet, compare a local block with Blockstream, and submit an already signed transaction. The image boots with **all outbound traffic blocked**. A local operator can enable Tor or cut off an active session. The separate offline signing project is named **refugium-offline-os**.

## Run the VM

The first target is x86-64 Linux with QEMU, OVMF firmware and a text console. From the repository root, use the boot image produced by the build below.

```sh
scripts/run .work/refugium-online-os.img .work/instance
```

The launcher creates a private state directory, firmware variables and a sparse 8 GiB data disk. Public signet starts from genesis on a fresh disk and prunes old block data. Subsequent boots reuse the local chain. Add `--gui` for a window. Enter commands in the guest.

| Command | Result |
| --- | --- |
| `status` | Shows the link state, Tor bootstrap progress, signet peers and local chain height. |
| `connect` | Allows the fixed Bitcoin and Blockstream paths through Tor. Bootstrap and initial sync take time. |
| `compare` | Reads Blockstream’s signet tip and compares hashes at the lower of the local and explorer heights. A partial sync can agree at that earlier height. |
| `broadcast` | Accepts signed transaction hex in short lines, terminated by a line containing a period. The synced local node checks it and shows the fee, virtual size and transaction ID. To submit, enter `send` and the full displayed ID. An ambiguous receipt calls for checking that ID before trying again. |
| `lock` | Closes Ethernet and IP egress, brings the uplink down and stops Tor and active explorer requests. Local node queries continue. |
| `poweroff` | Cuts the network and shuts the node down cleanly. |

For an entire session without network hardware, start with `scripts/run IMAGE STATE --sealed`. For an immediate, persistent cutoff controlled **outside** the guest, run the following on the host. Use the same state directory as the launcher.

```sh
scripts/gate seal .work/instance
```

This removes the running QEMU network backend. Later boots omit the virtual adapter. After powering off, `scripts/gate arm .work/instance` permits the next boot to have an adapter. It still starts locked and requires a fresh `connect`. The guest cannot override a host seal. A cutoff stops new traffic and cannot retract a previously transmitted transaction.

## What can leave

Only Tor can open a public IPv4 TCP connection, on port 443. The virtual gateway also needs local ARP. The Bitcoin service can ask a private proxy for nine pinned public signet peers on port 38333. A separate private socket takes the explorer only to `blockstream.info:443`. HTTPS verifies the hostname and certificate, and the client has three operations on the signet API. The image has no general-purpose browser, DNS client service, public RPC listener, or guest wallet. Public signet peer availability and Tor exit access can change. Operator time comes from the VM clock.

The host, guest kernel and packaged services are trusted. Application allowlists constrain destinations and operations. They do not inspect every possible use of data inside permitted Bitcoin messages. Use the host seal or start without an adapter whenever the requirement is zero transmission. The [spec](design/spec.md) records the trust boundary and upstream protocol references.

## Build

Build on x86-64 Linux with Python 3, bash, GNU make and coreutils, gcc, binutils, bc, bison, flex, Perl, pkg-config, OpenSSL and libelf development files. The image tools include bubblewrap with user namespaces, curl, tar, gzip, xz, zstd, GNU cpio, dosfstools and mtools. Running and testing also use QEMU, OVMF, OpenSSL and e2fsprogs.

```sh
scripts/fetch
JOBS=8 scripts/kernel
scripts/build
```

The fetcher checks the pinned Ubuntu Base, Linux and Bitcoin Core archive digests and downloads the locked package set from a signed Ubuntu snapshot. Image assembly runs without mounting or writing a raw host device. Use a new output path for a subsequent build.

## Acceptance

```sh
python3 -B tests/test_services.py
tests/isolated-network .work/refugium-online-os.img .work/network-test
```

The [acceptance record](evidence/acceptance.md) describes VM measurements and test boundaries. The [plan](design/plan.md) gives the review order. Large boot images, operator state and captures are local artifacts outside Git. This is a VM engineering preview for independent review. Bare hardware, Secure Boot signing and a distribution update mechanism are outside this checkpoint.
