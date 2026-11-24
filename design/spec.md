# Refugium Online OS

This x86-64 UEFI appliance runs three wallet-disabled nodes. An unpruned Bitcoin Core mainnet archive and a pruned public signet node share the Core executable. A separate pruned Bitcoin Satellite process receives mainnet blocks. A local operator uses its text console to control the link, query the node, compare a block with Blockstream's explorer, or submit an already signed signet transaction.

| State | Outbound behavior | Operator action |
| --- | --- | --- |
| Locked at boot | The guest interface is down. IPv4, forwarding and Ethernet policies drop external traffic. Loopback RPC remains available. | `connect` starts Tor for the Core peers and signet explorer. |
| Tor enabled | Only the Tor service can originate external IPv4 TCP to public port 443. The uplink also permits ARP between the VM and its gateway. Core can request the peers pinned for its own chain. The explorer can call fixed HTTPS operations on blockstream.info. | `lock` closes the firewall, drops the link and terminates both Tor and active explorer work. |
| Host sealed | The host removes the user-mode network backend. A persistent marker omits the adapter on subsequent boots. `--sealed` omits it for one invocation. | Re-arm a powered-off instance explicitly. Its next boot starts locked. |

The operator can keep the machine sealed indefinitely. Sealing ends Internet downloads. Blocks received on the one-way radio port can continue to advance both mainnet nodes. A cutoff cannot retract data already delivered.

## Application traffic

Each upstream Core node uses a separate Unix SOCKS socket. The peer service checks the connecting UID, SOCKS operation, destination and port against the packaged seed list for that node’s chain before passing a connection to Tor. DNS seeds, direct connections from the node, inbound P2P, discovery and wallets are disabled. Tor bootstrap and circuit maintenance are necessary transport traffic.

The explorer resolves `blockstream.info` through Tor and verifies the HTTPS certificate and hostname. It offers a tip-height query, a block hash at a numeric height, and submission of a signed transaction to the signet API. Redirects, user-supplied URLs and arbitrary POST endpoints are outside the interface. Comparison uses a common height and reports both tips. A matching block while the local node is catching up is labeled with the actual comparison height. Broadcast requires a synced local node, successful local mempool validation and operator confirmation of the computed transaction ID. An interrupted POST has an unknown outcome.

## Satellite input and storage

The host adapter accepts decapsulated UDP multicast from an operator-selected interface and optionally filters the source IPv4 address. The guest receives length-prefixed datagrams over virtio serial. The return side of that port terminates at the host’s null device. An unprivileged guest process can send only to the receiver’s IPv4 loopback multicast group. The receiver has no Internet peer, general proxy or web access. Its IPv4 multicast socket patch preserves the image’s lack of IPv6 and packet sockets.

The archive and receiver use separate Unix users, directories, RPC credentials and ports on the mainnet disk. A local relay can read chain information, block hashes and raw blocks from the receiver. It can read chain information and hashes from the archive and submit complete blocks for Core validation. It follows greater cumulative work, finds the common ancestor on a fork, and reports missing pruned history. The archive disables assumed-valid script shortcuts. The relay never supplies data to signet. The signet disk and public signet explorer workflow retain their own credentials and chain.

## Trust and scope

The guest kernel, supervisor, Bitcoin Core, Tor, application code and host hypervisor are trusted. The application rules constrain which services and destinations can communicate. They cannot prove that the contents of an allowed Bitcoin or HTTPS message contain no other information. A hostile guest administrator could change guest policy. The host seal removes the uplink outside the guest.

The first hardware target is QEMU with OVMF, an optional virtio network adapter with static user-mode NAT, and a separate receive-only radio port. The secret-handling offline stick has a separate repository and VM. The public build contains no signing wallets, operator files or host chain snapshot.

Protocol references come from [Bitcoin Core's signet seed list](https://github.com/bitcoin/bitcoin/blob/v31.1/contrib/seeds/nodes_signet.txt), the [Tor client documentation](https://github.com/bitcoin/bitcoin/blob/v31.1/doc/tor.md), [Blockstream's Esplora API](https://github.com/Blockstream/esplora/blob/master/API.md), the [nftables manual](https://netfilter.org/projects/nftables/manpage.html) and the [QEMU network documentation](https://www.qemu.org/docs/master/system/qemu-manpage.html).
