"""Disposable loopback account/permission/rotation proof; requires Docker and nats-py."""
import asyncio
import json
import secrets
import subprocess
import tempfile
import uuid
from pathlib import Path

import nats


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT).strip()


async def main():
    name = 'notes-nats-security-' + uuid.uuid4().hex[:8]
    password = secrets.token_hex(24)
    connections = []
    with tempfile.TemporaryDirectory() as directory:
        config_file = Path(directory) / 'server.json'
        publisher = lambda user: {'user': user, 'password': password, 'permissions': {
            'publish': ['orders.*.created'], 'subscribe': ['_INBOX.>']}}
        config = {'port': 4222, 'jetstream': {'store_dir': '/data'}, 'accounts': {
            'ORDERS_APP': {'jetstream': 'enabled', 'users': [
                {'user': 'admin', 'password': password}, publisher('api-v1'), publisher('api-v2')]},
            'ANALYTICS': {'jetstream': 'enabled', 'users': [{'user': 'analyst', 'password': password}]}}}
        config_file.write_text(json.dumps(config))
        try:
            docker('run', '--rm', '-d', '--name', name, '-p', '127.0.0.1::4222',
                   '-v', f'{directory}:/config:ro', 'nats:2.14.6', '-c', '/config/server.json')
            port = json.loads(docker('inspect', name))[0]['NetworkSettings']['Ports']['4222/tcp'][0]['HostPort']
            url = f'nats://127.0.0.1:{port}'

            async def connect(user, errors=None):
                async def on_error(error):
                    if errors is not None: errors.append(error)
                nc = await nats.connect(url, user=user, password=password, error_cb=on_error,
                                        connect_timeout=2, max_reconnect_attempts=0,
                                        allow_reconnect=False)
                connections.append(nc)
                return nc

            async with asyncio.timeout(10):
                while True:
                    try:
                        admin = await connect('admin')
                        break
                    except OSError:
                        await asyncio.sleep(.1)
            await admin.jetstream().add_stream(name='ORDERS', subjects=['orders.>'])
            errors = []
            old = await connect('api-v1', errors)
            new = await connect('api-v2')
            await old.jetstream().publish('orders.eu.created', b'evt-1')
            await new.jetstream().publish('orders.eu.created', b'evt-2')
            await old.publish('orders.eu.refund-approved', b'must-not-store')
            await old.flush(timeout=2)
            async with asyncio.timeout(2):
                while not errors: await asyncio.sleep(.01)
            assert any('permissions violation' in str(error).lower() for error in errors), errors
            analyst = await connect('analyst')
            seen = []
            async def received(message): seen.append(message.data)
            await analyst.subscribe('orders.eu.created', cb=received)
            await analyst.flush()
            await new.jetstream().publish('orders.eu.created', b'evt-3')
            await admin.flush()
            await asyncio.sleep(.1)
            assert not seen, seen
            config['accounts']['ORDERS_APP']['users'] = config['accounts']['ORDERS_APP']['users'][::2]
            # Keep admin and api-v2; remove api-v1, then reload the mounted configuration.
            config_file.write_text(json.dumps(config))
            docker('kill', '--signal', 'HUP', name)
            await asyncio.sleep(.2)
            denied = False
            try:
                await connect('api-v1')
            except nats.errors.Error:
                denied = True
            assert denied, 'retired identity authenticated'
            await new.jetstream().publish('orders.eu.created', b'evt-4')
            info = await admin.jetstream().stream_info('ORDERS')
            assert info.state.messages == 4, info.state.messages
            print('PASS: created allowed; refund denied; accounts isolated; v1 revoked; v2 works')
        finally:
            for nc in connections:
                await nc.close()
            subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True)


if __name__ == '__main__':
    asyncio.run(main())
