# Initial build and acceptance

1. Pin Ubuntu Noble, the Linux kernel, Bitcoin Core and the signed Ubuntu package snapshot. Build a new read-only UEFI boot disk and a separate writable chain disk.
2. Start fail-closed. Boot the normal image with an independent Ethernet capture and record the frame count before the first connect. Verify a sealed boot can access the local node and refuses network activation.
3. Enforce the Tor process rule, the signet destination checks and fixed explorer API. Test rejected SOCKS requests, certificate and redirect handling, and transaction confirmation against local fixtures.
4. Enable the production configuration. Verify public Tor bootstrap, signet block validation and a fixed-height HTTPS comparison. Confirm local data remains available when the guest lock interrupts live traffic.
5. Remove the host network backend during an active connection. Confirm the host latch survives a new boot, that a running guest cannot re-arm it and that an explicit powered-off re-arm returns to the locked startup state.
6. Prepare the source, evidence, tagged Git bundle and artifact hashes for independent coordinator review.
