# Refugium Online OS

This x86-64 UEFI appliance runs a wallet-disabled Bitcoin Core on public signet. A local operator uses its text console to control the link, query the node, compare a block with Blockstream's explorer, or submit an already signed signet transaction.

| State | Outbound behavior | Operator action |
| --- | --- | --- |
| Locked at boot | The guest interface is down. IPv4, forwarding and Ethernet policies drop external traffic. Loopback RPC remains available. | `connect` starts Tor and enables the two application paths. |
| Tor enabled | Only the Tor service can originate external IPv4 TCP to public port 443. The uplink also permits ARP between the VM and its gateway. Core can request specific signet peers. The explorer can call fixed HTTPS operations on blockstream.info. | `lock` closes the firewall, drops the link and terminates both Tor and active explorer work. |
| Host sealed | The host removes the user-mode network backend. A persistent marker omits the adapter on subsequent boots. `--sealed` omits it for one invocation. | Re-arm a powered-off instance explicitly. Its next boot starts locked. |

The operator can keep the machine sealed indefinitely. A state that transmits zero packets cannot maintain a TCP/Tor session or continue downloading blocks. Existing chain data remains available locally. A cutoff cannot retract data already delivered.

## Application traffic

The node uses a Unix SOCKS socket. The peer service checks the connecting UID, SOCKS operation, destination and port against the packaged signet seed list before passing a connection to Tor. DNS seeds, direct connections from the node, inbound P2P, discovery and wallets are disabled. Tor bootstrap and circuit maintenance are necessary transport traffic.

The explorer resolves `blockstream.info` through Tor and verifies the HTTPS certificate and hostname. It offers a tip-height query, a block hash at a numeric height, and submission of a signed transaction to the signet API. Redirects, user-supplied URLs and arbitrary POST endpoints are outside the interface. Comparison uses a common height and reports both tips. A matching block while the local node is catching up is labeled with the actual comparison height. Broadcast requires a synced local node, successful local mempool validation and operator confirmation of the computed transaction ID. An interrupted POST has an unknown outcome.

## Trust and scope

The guest kernel, supervisor, Bitcoin Core, Tor, application code and host hypervisor are trusted. The application rules constrain which services and destinations can communicate. They cannot prove that the contents of an allowed Bitcoin or HTTPS message contain no other information. A hostile guest administrator could change guest policy. The host seal removes the uplink outside the guest.

The first hardware target is QEMU with OVMF, one virtio network adapter and static user-mode NAT. The secret-handling offline stick has a separate repository and VM. The public build contains no signing wallets, operator files or host chain snapshot.

Protocol references come from [Bitcoin Core's signet seed list](https://github.com/bitcoin/bitcoin/blob/v31.1/contrib/seeds/nodes_signet.txt), the [Tor client documentation](https://github.com/bitcoin/bitcoin/blob/v31.1/doc/tor.md), [Blockstream's Esplora API](https://github.com/Blockstream/esplora/blob/master/API.md), the [nftables manual](https://netfilter.org/projects/nftables/manpage.html) and the [QEMU network documentation](https://www.qemu.org/docs/master/system/qemu-manpage.html).
