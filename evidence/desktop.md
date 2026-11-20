# Desktop VM acceptance

On November 20, 2026 the x86-64 UEFI image booted into Openbox. The default terminal showed all three node heights and satellite reception. After a window close and a fresh boot, the sealed VM recovered the signet test chain at height 331,658 and again reported incoming radio packets. The running demo uses a copy of the existing signet test disk. Its small mainnet test disk starts at genesis.

The bottom dock launched mr-gui 0.1.0-alpha.1 and Mousepad. The wallet selected signet at the local RPC port and read its cookie. On a fresh signet disk it correctly reported initial sync. Selecting all text in Mousepad and copying produced a guest clipboard byte-for-byte identical to the supplied 2,417-byte fixture. Git contains neither the supplied binary nor the fixture.

Guest Firefox rendered the packaged Esplora and mempool.space pages with WAN absent. Both HTTP roots and the mempool backend information route returned 200. The latter identified version 3.3.2. The local WebSocket handshake returned 101 and both frontend listeners refused a transaction POST with 405. Both pages use the local archive. The mainnet index was waiting for Bitcoin Core to finish initial sync. In a separate network-isolated four-block regtest, the packaged electrs binary with the shipping RPC allowlist returned the generated tip hash and block details. This run did not exercise a fully synced mainnet index or verify mainnet fee estimates.

The disposable firewall test exercised 13 UIDs with egress locked, enabled and relocked. External capture recorded only the Tor account's TCP 443 probe in the enabled phase. The test also checked the allowed loopback ports for the operator, web service, indexer and mempool backend. Six peer/explorer protocol tests and four block-relay tests passed.

The display follow-up booted at 1920 × 1080. Openbox reported a 1920 × 1018 work area above the 62-pixel dock. The maximized wallet client measured 1920 × 999 beneath its 19-pixel title bar. In the visible VM, the rightmost navigation button, Retry, Show details and the lower-right footer were all visible at once.

The launcher update adds Terminal as the sixth dock entry. Clicking it opened Bash 5.2.21 as the desktop operator (UID 914) in the operator’s home directory, with a guest pseudoterminal. The test ran a command and exited the shell. Clicking the shield launched the wallet. The dock uses the crop defined by mr-gui’s `Shield` component from `crates/mr-gui/ui/img/logo.png`, scaled into a 128-pixel square. The installed application entries matched those used by the dock.

The Ubuntu iputils-ping package was exercised from the Terminal launcher as UID 914. In the sealed guest, loopback echo reported 100% packet loss and an external numeric address reported no route. In the independent restricted-network test, the same operator received a loopback echo reply before firewall installation. With the rules active, loopback and external echo failed in each of the three phases. The external capture contained no outbound ICMP.

The desktop release inputs are pinned by digest in [assets.lock](../image/desktop/assets.lock) and [packages.lock](../image/desktop/packages.lock). The released explorer code comes from [Blockstream Esplora](https://github.com/Blockstream/esplora), [mempool](https://github.com/mempool/mempool) and [mempool electrs](https://github.com/mempool/electrs).

With the optional host clipboard enabled on a sealed graphical boot, a private host X display copied sample text into the guest. Ctrl+Shift+V pasted the exact string into the dock Terminal. A second sample copied in the guest arrived byte-for-byte on the private host display. QEMU reported the clipboard port open and no Internet backend. A separate boot of the release image also reported an open clipboard port, zero network adapters and locked guest status.

On a sealed desktop boot, the dock Terminal found the public test fixture, the wallet executable on the `/opt` bind mount and the signet configuration by name. The operator created a file in its home, ran `updatedb` without elevated privileges and found the new file with `locate`. A query for a fixture inside a root-only directory returned zero matches and exit status 1.

The dock renders all six launchers at 48 × 48 guest pixels. Each composited icon matched its corresponding rectangle in the 1920 × 1080 guest framebuffer pixel for pixel. The desktop work area remained 1920 × 1018. Clicking Terminal and the wallet shield opened their respective applications.
