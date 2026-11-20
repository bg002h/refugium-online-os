from pathlib import Path

TOR, FILTER, BITCOIN, WEB, OPERATOR = range(910, 915)
APP = Path('/usr/lib/refugium-online')
CONTROL = Path('/run/refugium/control.sock')
PEER_SOCKET = Path('/run/peer-filter/socks')
SITE_SOCKET = Path('/run/site-filter/https')
EXPLORER_HOST = 'blockstream.info'
PEERS = Path('/etc/refugium-online/peers')
CLI = ['/usr/local/bin/bitcoin-cli', '-datadir=/run/bitcoin-client',
       '-conf=/etc/refugium-online/bitcoin.conf']
ARCHIVE, SATELLITE, RELAY, RADIO = range(915, 919)
ARCHIVE_SOCKET = Path('/run/main-peer/socks')
ARCHIVE_PEERS = Path('/etc/refugium-online/mainnet-peers')
