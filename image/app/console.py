"""Local console. Commands are sent to the supervisor over a protected Unix socket."""
import asyncio
import json
import sys

from settings import CONTROL
from explorer import MAX_HEX


async def call(command, **fields):
    reader, writer = await asyncio.open_unix_connection(CONTROL, limit=1_000_000)
    try:
        writer.write(json.dumps(dict(command=command, **fields)).encode() + b'\n')
        await writer.drain()
        return json.loads(await reader.readline())
    finally:
        writer.close()
        await writer.wait_closed()


async def console():
    terminal = asyncio.StreamReader(limit=MAX_HEX+64)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(terminal), sys.stdin)

    async def line():
        data = await terminal.readline()
        if not data:
            raise EOFError
        return data.decode().strip()

    async def show(command, **fields):
        try:
            result = await call(command, **fields)
            print(json.dumps(result, sort_keys=True), flush=True)
        except (OSError, ValueError) as error:
            print(f'Control unavailable: {error}', flush=True)

    pending = set()
    print('Refugium Online OS | signet\nstatus  connect  lock  compare  broadcast  poweroff', flush=True)
    while True:
        try:
            command = await line()
            if command in ('status', 'connect', 'lock', 'poweroff'):
                await show(command)
            elif command == 'compare':
                task = asyncio.create_task(show(command))
                pending.add(task)
                task.add_done_callback(pending.discard)
            elif command == 'broadcast':
                print('Paste signed signet transaction hex in short lines. End with a period on its own line. Type lock to cancel and cut traffic.', flush=True)
                parts, length = [], 0
                while True:
                    part = await line()
                    if part == 'lock':
                        await show('lock')
                        break
                    if part == '.':
                        raw = ''.join(parts)
                        result = await call('preview', raw=raw)
                        print(json.dumps(result), flush=True)
                        if 'txid' in result:
                            print('Type send followed by the full transaction ID, or lock to cancel and cut traffic.', flush=True)
                            confirmation = await line()
                            if confirmation == 'lock':
                                await show('lock')
                            elif confirmation == 'send ' + result['txid']:
                                task = asyncio.create_task(show('broadcast', raw=raw, confirm=result['txid']))
                                pending.add(task)
                                task.add_done_callback(pending.discard)
                            else:
                                print('Cancelled', flush=True)
                        break
                    length += len(part)
                    if length > MAX_HEX:
                        print('Transaction too large', flush=True)
                        break
                    parts.append(part)
            elif command:
                print('status  connect  lock  compare  broadcast  poweroff', flush=True)
        except EOFError:
            return
        except (ValueError, OSError) as error:
            print(str(error), flush=True)


if __name__ == '__main__':
    asyncio.run(console())
