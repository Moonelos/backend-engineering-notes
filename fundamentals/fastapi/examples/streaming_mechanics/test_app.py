import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from .app import app, OwnedStream


def test_upstream_status_before_response_start():
    with TestClient(app) as client:
        assert client.get('/events?fail=true').status_code == 502
        response = client.get('/events')
        assert response.status_code == 200
        assert 'café' in response.text
    assert app.state.client.is_closed


def test_incremental_forward_and_cancel_cleanup():
    async def scenario():
        first_sent = asyncio.Event()
        release_second = asyncio.Event()
        class Body(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                yield b'A'
                await release_second.wait()
                yield b'B'
            async def aclose(self):
                self.closed = True
        body = Body()
        response = httpx.Response(200, stream=body)
        messages = []
        async def send(message):
            messages.append(message)
            if message.get('body') == b'A': first_sent.set()
        async def receive():
            await asyncio.Event().wait()
        task = asyncio.create_task(OwnedStream(response)(
            {'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send))
        await asyncio.wait_for(first_sent.wait(), .5)
        assert not task.done() and not body.closed
        assert [m.get('body') for m in messages if m['type'] == 'http.response.body'] == [b'A']
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert body.closed and response.is_closed
    asyncio.run(scenario())


def test_post_start_failure_propagates_and_closes():
    async def scenario():
        class Broken(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                yield b'A'
                raise RuntimeError('failed after headers')
            async def aclose(self): self.closed = True
        body = Broken()
        sent = []
        async def send(message): sent.append(message)
        async def receive(): await asyncio.Event().wait()
        with pytest.raises(RuntimeError, match='failed after headers'):
            await OwnedStream(httpx.Response(200, stream=body))(
                {'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send)
        assert sum(m['type'] == 'http.response.start' for m in sent) == 1
        assert not any(m['type'] == 'http.response.body' and not m.get('more_body') for m in sent)
        assert body.closed
    asyncio.run(scenario())
