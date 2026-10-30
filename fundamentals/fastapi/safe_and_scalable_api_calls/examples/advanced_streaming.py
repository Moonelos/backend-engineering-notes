"""Finite SSE laboratory: explicit owner, one iterator, bounded frames and lifecycle."""
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from starlette.responses import Response
from bounded_calls import AdmissionTimeout


async def finish(awaitable):
    """Own cleanup even when the parent is cancelled again while joining it."""
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


class WeightedGate:
    def __init__(self, capacity, max_waiters=10):
        if capacity < 1 or max_waiters < 0:
            raise ValueError('Invalid capacity')
        self.capacity, self.max_waiters = capacity, max_waiters
        self.used = self.waiting = 0
        self.changed = asyncio.Condition()

    @asynccontextmanager
    async def lease(self, weight=1, timeout=1):
        if not isinstance(weight, int) or not 1 <= weight <= self.capacity:
            raise ValueError('Weight must fit the whole gate')
        acquired = False
        try:
            async with asyncio.timeout(timeout):
                async with self.changed:
                    if self.used + weight > self.capacity:
                        if self.waiting >= self.max_waiters:
                            raise AdmissionTimeout('Waiting capacity exhausted')
                        self.waiting += 1
                        try:
                            await self.changed.wait_for(lambda: self.used + weight <= self.capacity)
                        finally:
                            self.waiting -= 1
                    self.used += weight  # All units acquired atomically.
                    acquired = True
            yield
        finally:
            if acquired:
                async def release():
                    async with self.changed:
                        self.used -= weight
                        self.changed.notify_all()
                await finish(release())


@dataclass(frozen=True)
class Frame:
    kind: str
    data: dict | None = None

    def encode(self, source=None):
        payload = {**(self.data or {}), 'source': source} if source else (self.data or {})
        if self.kind == 'done':
            if source:
                return f'event: done\ndata: {json.dumps({"source": source, "done": True})}\n\n'.encode()
            return b'event: done\ndata: [DONE]\n\n'
        return f'event: {self.kind}\ndata: {json.dumps(payload)}\n\n'.encode()


class StreamOwner:
    """Owns response and the SAME byte iterator from first frame until close."""
    def __init__(self, client, path, *, idle=30, max_frame=4096, max_bytes=262144):
        self.client, self.path, self.idle, self.max_frame = client, path, idle, max_frame
        self.max_bytes, self.bytes_read = max_bytes, 0
        self.response = self.iterator = None
        self.buffer = bytearray()
        self.outcome = 'unknown'
        self.closed = False

    async def open(self):
        try:
            request = self.client.build_request('GET', self.path, headers={'Accept-Encoding': 'identity'})
            self.response = await self.client.send(request, stream=True)
            self.response.raise_for_status()
            if self.response.headers.get('content-encoding', 'identity') != 'identity':
                raise ValueError('Unsupported encoding')
            if not self.response.headers.get('content-type', '').startswith('text/event-stream'):
                raise ValueError('Unexpected content type')
            self.iterator = self.response.aiter_raw().__aiter__()
            return self
        except BaseException:
            await finish(self.close())
            raise

    async def next(self):
        # This fixture's provider contract is one LF-delimited data field per frame.
        # It deliberately rejects other SSE fields/multiline data instead of misparsing them.
        async with asyncio.timeout(self.idle):
            while b'\n\n' not in self.buffer:
                try:
                    chunk = await anext(self.iterator)
                except StopAsyncIteration:
                    return None  # EOF without done remains unknown.
                self.bytes_read += len(chunk)
                if self.bytes_read > self.max_bytes:
                    raise ValueError('Provider stream exceeds byte budget')
                self.buffer.extend(chunk)
                if len(self.buffer) > self.max_frame:
                    raise ValueError('Provider frame/buffer too large')
            raw, _, tail = self.buffer.partition(b'\n\n')
            self.buffer = bytearray(tail)
            if not raw.startswith(b'data: ') or b'\n' in raw:
                raise ValueError('Unsupported SSE frame')
            payload = raw[6:]
            if payload == b'[DONE]':  # Terminal marker before JSON decoding.
                self.outcome = 'done'
                return Frame('done')
            obj = json.loads(payload)
            if not isinstance(obj, dict) or not isinstance(obj.get('text'), str):
                raise ValueError('Unexpected delta')
            return Frame('delta', obj)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.response is not None:
            await self.response.aclose()


class FiniteSSE(Response):
    media_type = 'text/event-stream'

    def __init__(self, client, gate, *, path='/ok', total=90, idle=30,
                 admission=1, first=5, send_timeout=5, stats=None):
        super().__init__(content=b'', media_type=self.media_type)
        self.client, self.gate, self.path = client, gate, path
        self.total, self.idle, self.admission, self.first = total, idle, admission, first
        self.send_timeout, self.stats = send_timeout, stats if stats is not None else {}

    async def __call__(self, scope, receive, send):
        owner = StreamOwner(self.client, self.path, idle=self.idle)
        started = False

        async def bounded_send(message):
            async with asyncio.timeout(self.send_timeout):
                await send(message)

        async def run():
            nonlocal started
            try:
                async with asyncio.timeout(self.total):
                    async with self.gate.lease(timeout=self.admission):
                        try:
                            async with asyncio.timeout(self.first):
                                await owner.open()
                                frame = await owner.next()
                                if frame is None or frame.kind != 'delta':
                                    raise ValueError('Empty candidate')
                            await bounded_send({'type': 'http.response.start', 'status': 200,
                                'headers': [(b'content-type', b'text/event-stream'),
                                            (b'cache-control', b'no-cache'), (b'x-accel-buffering', b'no')]})
                            started = True
                            while frame is not None:
                                await bounded_send({'type': 'http.response.body', 'body': frame.encode(),
                                                    'more_body': True})
                                if frame.kind == 'done':
                                    break
                                frame = await owner.next()
                            if owner.outcome != 'done':
                                raise ValueError('Missing terminal event')
                        finally:
                            await finish(owner.close())  # Before releasing admission.
                await bounded_send({'type': 'http.response.body', 'body': b'', 'more_body': False})
            except asyncio.CancelledError:
                owner.outcome = 'cancelled'
                raise
            except (TimeoutError, AdmissionTimeout, httpx.HTTPError, ValueError, UnicodeError):
                if owner.outcome != 'done':
                    owner.outcome = 'failed'
                try:
                    if not started:
                        await bounded_send({'type': 'http.response.start', 'status': 503,
                                            'headers': [(b'content-type', b'application/json')]})
                        body = b'{"error":"stream_unavailable"}'
                    else:
                        body = Frame('error', {'code': 'stream_interrupted'}).encode()
                    await bounded_send({'type': 'http.response.body', 'body': body, 'more_body': False})
                except (TimeoutError, OSError):
                    pass  # The disconnected/slow client cannot receive an error.
            finally:
                try:
                    await finish(owner.close())
                finally:
                    # Disconnect can arrive after the final body send while cleanup joins.
                    key = owner.outcome
                    self.stats[key] = self.stats.get(key, 0) + 1

        async def disconnected():
            while (await receive())['type'] != 'http.disconnect':
                pass

        work = asyncio.create_task(run(), name='finite-sse-owner')
        watch = asyncio.create_task(disconnected(), name='finite-sse-disconnect')
        try:
            done, _ = await asyncio.wait({work, watch}, return_when=asyncio.FIRST_COMPLETED)
            if watch in done and not work.done():
                work.cancel()
            await asyncio.gather(work, return_exceptions=False)
        except asyncio.CancelledError:
            # A normal client disconnect cancels the owned work; server cancellation propagates.
            if not watch.done():
                raise
        finally:
            work.cancel()
            watch.cancel()
            await finish(asyncio.gather(work, watch, return_exceptions=True))


class DemoBytes(httpx.AsyncByteStream):
    def __init__(self, mode='ok', delay=.02):
        self.mode, self.delay, self.closed = mode, delay, False
    async def __aiter__(self):
        if self.mode == 'empty':
            return
        for index in range(1000 if self.mode == 'drip' else 3):
            await asyncio.sleep(self.delay)
            yield f'data: {{"text":"{index}"}}\n\n'.encode()
        yield b'data: [DONE]\n\n'
    async def aclose(self):
        self.closed = True


def demo_transport(streams):
    async def handle(request):
        mode = request.url.path.strip('/')
        stream = DemoBytes(mode)
        streams.append(stream)
        return httpx.Response(503 if mode == 'bad' else 200,
            headers={'content-type': 'text/event-stream'}, stream=stream)
    return httpx.MockTransport(handle)
