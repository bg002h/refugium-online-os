"""Give Bitcoin Core a SOCKS5 socket restricted to the pinned signet peers."""
import asyncio
import ipaddress
import os
import socket
import struct

from settings import ARCHIVE, ARCHIVE_PEERS, ARCHIVE_SOCKET, BITCOIN, EXPLORER_HOST, PEERS, PEER_SOCKET, SITE_SOCKET, WEB

DENY = b'\x05\x02\0\x01' + bytes(6)


async def address(reader, kind):
    if kind == 1:
        return str(ipaddress.IPv4Address(await reader.readexactly(4)))
    if kind == 3:
        size = (await reader.readexactly(1))[0]
        return (await reader.readexactly(size)).decode('ascii')
    raise ValueError('Unsupported address type')


async def handshake(reader, writer, peers):
    version, count = await reader.readexactly(2)
    if version != 5 or 0 not in await reader.readexactly(count):
        raise ValueError('Unsupported SOCKS negotiation')
    writer.write(b'\x05\0')
    await writer.drain()
    version, command, reserved, kind = await reader.readexactly(4)
    if (version, command, reserved) != (5, 1, 0):
        raise ValueError('Only CONNECT is supported')
    name = await address(reader, kind)
    port = int.from_bytes(await reader.readexactly(2), 'big')
    if f'{name}:{port}' not in peers:
        raise ValueError('Destination refused')
    return name.encode('ascii'), port


async def pump(reader, writer):
    while chunk := await reader.read(65536):
        writer.write(chunk)
        await writer.drain()


async def open_tor_stream(name, port, listener):
    upstream, remote = await asyncio.open_connection('127.0.0.1', listener)
    try:
        remote.write(b'\x05\x01\0')
        await remote.drain()
        if await upstream.readexactly(2) != b'\x05\0':
            raise ValueError('Tor unavailable')
        remote.write(b'\x05\x01\0\x03' + bytes([len(name)]) + name + port.to_bytes(2, 'big'))
        await remote.drain()
        version, result, reserved, kind = await upstream.readexactly(4)
        if (version, result, reserved) != (5, 0, 0):
            raise ValueError('Destination unavailable')
        await address(upstream, kind)
        await upstream.readexactly(2)
        return upstream, remote
    except BaseException:
        remote.close()
        raise


async def serve(reader, writer, peers=None, client_uid=BITCOIN):
    """The socket selects the policy. Only the Core socket accepts a destination."""
    remote = None
    tasks = []
    try:
        creds = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        uid = struct.unpack('3i', creds)[1]
        if peers is None:
            if uid != WEB:
                return
            name, port, listener = EXPLORER_HOST.encode('ascii'), 443, 9051
        else:
            if uid != client_uid:
                return
            name, port = await asyncio.wait_for(handshake(reader, writer, peers), 10)
            listener = 9050
        upstream, remote = await asyncio.wait_for(open_tor_stream(name, port, listener), 75)
        if peers is not None:
            writer.write(b'\x05\0\0\x01' + bytes(6))
            await writer.drain()
        tasks = [asyncio.create_task(pump(reader, remote)), asyncio.create_task(pump(upstream, writer))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, ValueError, EOFError, TimeoutError):
        if peers is not None and not tasks:
            writer.write(DENY)
    finally:
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for stream in [remote, writer]:
            if stream is not None:
                stream.close()


async def main():
    peers = set(PEERS.read_text().splitlines())
    for path in (PEER_SOCKET, ARCHIVE_SOCKET, SITE_SOCKET):
        path.unlink(missing_ok=True)
    core = await asyncio.start_unix_server(lambda r, w: serve(r, w, peers), PEER_SOCKET)
    main_peers = set(ARCHIVE_PEERS.read_text().splitlines())
    archive = await asyncio.start_unix_server(lambda r,w: serve(r,w,main_peers,ARCHIVE), ARCHIVE_SOCKET)
    web = await asyncio.start_unix_server(serve, SITE_SOCKET)
    for path in (PEER_SOCKET, ARCHIVE_SOCKET, SITE_SOCKET):
        os.chmod(path, 0o660)
    async with core, archive, web:
        await asyncio.gather(core.serve_forever(), archive.serve_forever(), web.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())
