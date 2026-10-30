import asyncio
import os
import time

os.environ.setdefault('WS_SESSION_SECRET', 'local-test-only-' + 'x' * 32)
from fastapi.testclient import TestClient
from . import app as module


def test_signed_subscribe_and_ping():
    with TestClient(module.app) as client:
        client.cookies.set('session', module.sign_session('usr_123', int(time.time()) + 60))
        with client.websocket_connect('/ws/notifications',
                headers={'origin': 'https://app.example.com'},
                subprotocols=[module.SUBPROTOCOL]) as ws:
            ws.send_json({'version': 1, 'type': 'notifications.subscribe', 'message_id': 'm1'})
            assert ws.receive_json()['request_id'] == 'm1'
            ws.send_json({'version': 1, 'type': 'app.ping', 'message_id': 'm2'})
            assert ws.receive_json()['request_id'] == 'm2'
    assert not module.hub._clients


def test_invalid_signature_and_expiry():
    assert module.verify_session('usr_123.9999999999.é') is None
    assert module.verify_session('usr_123.9999999999.zz') is None
    assert module.verify_session(module.sign_session('usr_123', int(time.time()) - 1)) is None


def test_stalled_send_is_cancelled_and_capacity_isolated():
    class StalledSocket:
        cancelled = False
        async def send_json(self, value):
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    async def scenario():
        socket = StalledSocket()
        first = module.ClientConnection(socket, 'usr_123', subscribed=True)
        second = module.ClientConnection(StalledSocket(), 'usr_456', subscribed=True)
        hub = module.ConnectionHub()
        await hub.add(first)
        await hub.add(second)
        await hub.publish_to_user('usr_123', {'id': 'evt_1'})
        assert first.outbound.qsize() == 1
        assert second.outbound.empty()
        old = module.SEND_TIMEOUT
        module.SEND_TIMEOUT = .02
        try:
            await asyncio.wait_for(module.send_messages(first), .5)
        finally:
            module.SEND_TIMEOUT = old
        assert socket.cancelled and first.stop.is_set()
        assert first.close_code == 1013
        for _ in range(module.MAX_OUTBOUND_MESSAGES + 1):
            await hub.publish_to_user('usr_123', {'id': 'evt_2'})
        assert first.stop.is_set() and first.outbound.qsize() <= module.MAX_OUTBOUND_MESSAGES
        await hub.remove(first)
        assert first not in hub._clients
    asyncio.run(scenario())
