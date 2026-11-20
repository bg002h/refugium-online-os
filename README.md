# Refugium Online OS

Run an unpruned Bitcoin Core mainnet archive, a pruned Blockstream Satellite mainnet receiver and a separate public signet test node. The signet console can compare a local block with Blockstream and submit an already signed signet transaction. The image boots with **all outbound traffic blocked**. A local operator can enable Tor or cut off an active session. The separate offline signing project is named **refugium-offline-os**.

## Run the VM

The first target is x86-64 Linux with QEMU and OVMF firmware. The desktop build opens an Openbox session. From the repository root, use the boot image produced by the build below.

```sh
scripts/run .work/refugium-online-os.img .work/instance --gui
```

The launcher creates private firmware variables and two persistent sparse disks. The signet disk is 8 GiB. The mainnet disk defaults to 1536 GiB of logical capacity and grows as blocks are stored. An unpruned archive needs real backing space for the chain and future growth. For short VM tests, `--mainnet-size-gib 8` sets the size of a **new** disk. Existing disks retain their contents and size. All three nodes start at genesis on an empty instance. The desktop opens Node status in a terminal. It shows chain heights, block times, explorer index readiness, satellite reception, free disk space and outbound policy. Press Enter for the command console and type `screen` to return. The serial console is also available in headless mode.

The graphical VM uses a 1920 × 1080 guest desktop. The viewer scales it to fit its window, and mr-gui opens maximized above the dock.

The bottom dock opens **Node status**, **Esplora**, **mempool.space**, **mr-gui** and **Test public keys**, in that order. Both explorers run locally against the mainnet archive and share one electrs index. Firefox shows its welcome dialog on first use in a fresh session. The local pages open while the VM is sealed. Historical block and transaction lookups require the node to finish initial sync and electrs to index the blocks. The archive runs in blocks-only mode, so the live fee and mempool displays have limited data. Mining statistics, fiat prices and Lightning are disabled in this preview.

mr-gui reads the local signet cookie. The nodes have their wallets disabled. The public-keys launcher opens the complete build-supplied test fixture at `~/pubkeys` in Mousepad. Select and copy text there, then paste into another guest window. The live home directory is temporary.

| Command | Result |
| --- | --- |
| `screen` | Opens the live status screen. |
| `status` | Shows Tor state, each node’s chain height and peers, satellite input activity and block transfer status. |
| `connect` | Allows the fixed Bitcoin and Blockstream paths through Tor. Bootstrap and initial sync take time. |
| `compare` | Reads Blockstream’s signet tip and compares hashes at the lower of the local and explorer heights. A partial sync can agree at that earlier height. |
| `broadcast` | Accepts signed transaction hex in short lines, terminated by a line containing a period. The synced local node checks it and shows the fee, virtual size and transaction ID. To submit, enter `send` and the full displayed ID. An ambiguous receipt calls for checking that ID before trying again. |
| `lock` | Closes Ethernet and IP egress, brings the uplink down and stops Tor and active explorer requests. Local node queries continue. |
| `poweroff` | Cuts the network and stops all three nodes cleanly. |

For an entire session without network hardware, start with `scripts/run IMAGE STATE --sealed`. For an immediate, persistent cutoff controlled **outside** the guest, run the following on the host. Use the same state directory as the launcher.

```sh
scripts/gate seal .work/instance
```

This removes the running QEMU network backend. Later boots omit the virtual adapter. After powering off, `scripts/gate arm .work/instance` permits the next boot to have an adapter. It still starts locked and requires a fresh `connect`. The guest cannot override a host seal. A cutoff stops new traffic and cannot retract a previously transmitted transaction.

## Receive mainnet blocks with the Internet sealed

Keep the guest sealed for an entire session with `--sealed` or use the host gate during an outage. On the host, connect your already configured receiver’s demodulated IPv4 multicast stream to the running VM. Substitute its local interface address and the expected source address.

```sh
scripts/radio .work/instance --interface RECEIVER_INTERFACE_IPV4 --source GROUND_STATION_IPV4
```

The adapter listens for `239.0.0.2:4434` and carries datagrams into the VM through a one-way virtual serial port. The receiver decodes blocks into its own 2048 MiB prune target. The archive retrieves missing blocks locally and validates each one using Bitcoin Core. Signet has its own chain. `status` shows each mainnet tip and seconds since the last input datagram. A null age means no datagram has arrived this boot. A recent datagram alone cannot establish that new blocks are being decoded.

If the archive needs a block the receiver has already pruned, status gives the missing height. Restore independently validated archive history or explicitly enable Tor for catch-up. A receiver and archive that start together can retain the blocks the receiver later prunes. The physical receiver, reception and regional broadcast availability are operator inputs. [Blockstream receiver guide](https://blockstream.github.io/satellite/doc/bitcoin.html)

## What can leave

Only Tor can open a public IPv4 TCP connection, on port 443. The virtual gateway also needs local ARP. The two Core processes have separate private proxies. Signet can request nine pinned peers on port 38333. The mainnet archive can request six pinned onion peers on port 8333. A separate private socket takes the explorer only to `blockstream.info:443`. HTTPS verifies the hostname and certificate, and the client has three operations on the signet API. The guest browser can reach the two local explorer frontends. Its firewall policy denies direct Internet and Tor access. Bitcoin RPC listens on loopback, the nodes disable wallets, and the guest has no DNS client service. Public signet peer availability and Tor exit access can change. Operator time comes from the VM clock.

The host, guest kernel and packaged services are trusted. Application allowlists constrain destinations and operations. They do not inspect every possible use of data inside permitted Bitcoin messages. Use the host seal or start without an adapter whenever the requirement is zero transmission. The [spec](design/spec.md) records the trust boundary and upstream protocol references.

## Build

Build on x86-64 Linux with Python 3, patch, bash, GNU make and coreutils, gcc, binutils, bc, bison, flex, Perl, pkg-config, OpenSSL and libelf development files. The image tools include bubblewrap with user namespaces, curl, tar, gzip, xz, zstd, GNU cpio, dosfstools and mtools. Running and testing also use QEMU, OVMF, OpenSSL and e2fsprogs.

```sh
scripts/fetch
JOBS=8 scripts/kernel
JOBS=6 scripts/receiver
scripts/desktop-fetch
scripts/desktop-payload .work/desktop/inputs /path/to/mr-gui /path/to/test-pubkeys .work/desktop.ext4
scripts/build .work/inputs .work/kernel/arch/x86/boot/bzImage .work/refugium-online-os.img .work/inputs/bitcoin-satellite .work/desktop.ext4
```

The desktop payload builder also needs glib-compile-schemas, update-mime-database, a Noble-compatible x86-64 mr-gui executable and an explicitly supplied public test fixture. The fixture is readable by anyone with the image. Omit the final desktop filesystem argument from the build command for a serial appliance. The fetcher checks the Ubuntu Base, Linux, Bitcoin Core and Bitcoin Satellite archives and the locked Noble packages. The receiver builds without a wallet in an isolated, networkless Noble toolchain. Its build applies the IPv4 multicast patch required by the appliance kernel. Image assembly runs without mounting or writing a raw host device. Use a new output path for a subsequent build.

## Acceptance

```sh
python3 -B tests/test_services.py
python3 -B tests/test_blockrelay.py
tests/isolated-network .work/refugium-online-os.img .work/network-test
```

The [desktop acceptance record](evidence/desktop.md) covers the launchers, clipboard, local explorer services and firewall. The [three-node acceptance record](evidence/satellite.md) includes the sealed receiver test and its replay instructions. The [signet acceptance record](evidence/acceptance.md) covers the earlier signet checkpoint. The [plan](design/plan.md) gives the review order. Large boot images, operator state and captures are local artifacts outside Git. This is a VM engineering preview for independent review. Bare hardware, Secure Boot signing and a distribution update mechanism are outside this checkpoint.
