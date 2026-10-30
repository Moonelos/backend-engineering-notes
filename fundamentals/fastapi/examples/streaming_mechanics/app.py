import asyncio
from contextlib import asynccontextmanager

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import StreamingResponse


class UpstreamBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'id: 1\ndata: {"text":"caf\xc3\xa9"}\n\n'
        await asyncio.sleep(0.05)
        yield b'event: done\ndata: {}\n\n'


async def provider(request):
    if request.url.path == '/fail':
        return httpx.Response(503)
    return httpx.Response(200, stream=UpstreamBody(),
                          headers={'content-type': 'text/event-stream'})


async def bounded_close(response):
    # Shield cleanup against AnyIO cancellation, while bounding its own duration.
    with anyio.move_on_after(1, shield=True) as scope:
        await response.aclose()
    if scope.cancel_called:
        raise TimeoutError('upstream close exceeded one second')


class OwnedStream(StreamingResponse):
    def __init__(self, upstream):
        self.upstream = upstream
        super().__init__(upstream.aiter_raw(), media_type='text/event-stream',
                         headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    async def __call__(self, scope, receive, send):
        try:
            # Includes body forwarding, downstream backpressure and response finish.
            with anyio.fail_after(5):
                await super().__call__(scope, receive, send)
        finally:
            await bounded_close(self.upstream)


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider),
                                base_url='https://local-provider.invalid',
                                timeout=httpx.Timeout(2, pool=.2)) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


@app.get('/events')
async def events(request: Request, fail: bool = False):
    client = request.app.state.client
    upstream = None
    try:
        # Header deadline starts before the upstream request, before response.start.
        with anyio.fail_after(2):
            upstream = await client.send(client.build_request(
                'GET', '/fail' if fail else '/events',
                headers={'Accept-Encoding': 'identity'}), stream=True)
        upstream.raise_for_status()
        if upstream.headers.get('content-type', '').split(';')[0] != 'text/event-stream':
            raise HTTPException(502, 'unexpected upstream media type')
        if upstream.headers.get('content-encoding', 'identity') != 'identity':
            raise HTTPException(502, 'unexpected upstream encoding')
        return OwnedStream(upstream)
    except BaseException as error:
        if upstream is not None:
            await bounded_close(upstream)
        if isinstance(error, (httpx.HTTPError, TimeoutError)):
            raise HTTPException(502, 'upstream unavailable') from error
        raise
