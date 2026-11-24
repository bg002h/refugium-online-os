"""Live status on the appliance console. All readings come from the local supervisor."""
import asyncio
import shutil
import sys
from datetime import datetime, timezone


def quantity(value):
    return f'{value:,}' if isinstance(value, int) else '--'


def utc_tip(value):
    if not isinstance(value, int):
        return '--'
    return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%d %H:%M')


def status_rows(state):
    main = state.get('mainnet', {})
    sat = main.get('satellite', {})
    age = main.get('radio_last_datagram_age_seconds')
    group = next(iter((sat.get('multicast') or {}).values()), {})
    chunks = sat.get('partial_blocks') or {}
    total = group.get('rcvd_bytes')
    disks = state.get('disk_free_bytes', {})
    clock = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    rows = [('1;36', 'Refugium Online OS'), ('1;37', 'Node status'), ('37', 'Updated ' + clock), ('', '')]

    if 'error' in state:
        rows.append(('1;33', 'Status unavailable: ' + str(state['error'])))
    else:
        if state.get('mode') == 'tor':
            network = 'Enabled through Tor   |   Bootstrap ' + state.get('tor_bootstrap', 'starting')
        elif state.get('mode') == 'locked':
            network = 'Locked'
            if state.get('uplink') is None and not state.get('issue'):
                network += '   |   No Internet adapter'
        else:
            network = 'Unknown'
        rows.extend([('1;37', 'Outbound traffic    ' + network), ('', ''),
                     ('36', f'{"NODE":<22}{"HEIGHT":>10}{"PEERS":>8}    BEST BLOCK (UTC)')])
        for name, node, peers in [
            ('Mainnet archive', main.get('archive', {}), main.get('archive', {}).get('peers')),
            ('Satellite mainnet', sat, sat.get('peers')),
            ('Signet test node', state.get('node', {}), state.get('peers')),
        ]:
            if 'blocks' in node:
                text = f'{name:<22}{quantity(node["blocks"]):>10}{quantity(peers):>8}    {utc_tip(node.get("time"))}'
            else:
                text = f'{name:<22}  {node.get("issue", "Unavailable")}'
            rows.append(('37', text))

        if 'index_height' in state:
            index = state['index_height']
            waiting = ('Waiting for mainnet sync' if main.get('archive', {}).get('initialblockdownload')
                       else 'Waiting for indexer')
            rows.append(('37', 'Explorer index          ' + (f'{index:,}' if index is not None else waiting)))
        if not main.get('radio_input'):
            signal = 'Input unavailable'
        elif age is None:
            signal = 'Waiting for first packet'
        elif age > 10:
            signal = f'Last packet {age}s ago'
        else:
            signal = f'Receiving   |   Last packet {age}s ago'
        rate = group.get('bitrate', '--')
        if age is None or age > 10:
            rate = '--'
        else:
            try:
                value, unit = rate.split()
                rate = f'{float(value):.2f} {unit}'
            except ValueError:
                pass
        received = f'{total / 2**20:,.1f} MiB' if isinstance(total, int) else '--'
        rows.extend([('', ''), ('1;36', 'Satellite reception'), ('37', signal),
                     ('37', f'Rate   {rate}     Received   {received}'),
                     ('37', f'Partial blocks   {quantity(chunks.get("n_blks"))}     Chunks   {quantity(chunks.get("n_chunks"))}')])
        relay = main.get('relay', {})
        if relay.get('state'):
            relay_state = relay['state']
            if relay.get('required_height') is not None:
                relay_state += f' (needs height {relay["required_height"]:,})'
            rows.append(('37', 'Archive relay   ' + relay_state))
        rows.extend([('', ''), ('1;36', 'Free disk space')])
        for label, name in [('Mainnet', 'mainnet'), ('Signet', 'signet')]:
            free = disks.get(name)
            rows.append(('37', f'{label:<12}' + (f'{free / 2**30:,.2f} GiB' if free is not None else 'Unavailable')))
        if state.get('issue'):
            rows.append(('1;33', str(state['issue'])))
        for issue in main.get('issues', {}).values():
            rows.append(('1;33', str(issue)))
    return rows


def draw(state):
    columns, height = shutil.get_terminal_size((80, 25))
    width = min(77, columns - 2)
    left = ' ' * max(0, (columns - width) // 2)
    rows = status_rows(state)
    rows += [('', ''), ('1;37', 'Enter   Open command console')]
    top = max(0, min(4, (height - len(rows)) // 2))
    lines = ['\x1b[2K'] * top
    for color, label in rows:
        # Local RPC and error strings are data. Keep control characters off the screen.
        text = ''.join(c if c.isprintable() else ' ' for c in label)
        lines.append('\x1b[2K' + left + f'\x1b[{color or "0"}m' + text[:width] + '\x1b[0m')
    sys.stdout.write('\x1b[H' + '\n'.join(lines) + '\x1b[J')
    sys.stdout.flush()


async def watch_status(call, terminal):
    sys.stdout.write('\x1b[2J\x1b[H\x1b[?25l')
    pending = asyncio.create_task(terminal.readline())
    try:
        while not pending.done():
            try:
                state = await asyncio.wait_for(call('status'), 12)
            except (TimeoutError, OSError, ValueError) as error:
                state = {'error': str(error) or 'Local supervisor timed out'}
            draw(state)
            await asyncio.wait({pending}, timeout=2)
        pending.result()
    finally:
        pending.cancel()
        sys.stdout.write('\x1b[0m\x1b[?25h\x1b[2J\x1b[H')
        sys.stdout.flush()
