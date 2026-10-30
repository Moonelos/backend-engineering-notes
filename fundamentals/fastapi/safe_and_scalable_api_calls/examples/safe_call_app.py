"""A runnable local dependency-failure lab; default transport never contacts a provider."""
from contextlib import asynccontextmanager
import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from bounded_calls import (BoundedCaller, AdmissionTimeout, AttemptDeadlineExceeded,
                           TotalDeadlineExceeded, ProviderFailure)


def create_app(*, provider_mode='healthy'):
    async def provider(request):
        if provider_mode == 'outage':
            return httpx.Response(503)
        if provider_mode == 'slow':
            await asyncio.sleep(10)
        return httpx.Response(200, json={'order':'ord_42','status':'paid'})

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url='https://provider.test',
                transport=httpx.MockTransport(provider),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                timeout=httpx.Timeout(connect=1, read=1, write=1, pool=.1)) as client:
            app.state.caller = BoundedCaller(client, capacity=20, max_waiters=40,
                admission_timeout=.1, attempt_timeout=.2, jitter=lambda n: 0)
            app.state.accepting = True
            try:
                yield
            finally:
                app.state.accepting = False

    app = FastAPI(lifespan=lifespan)

    @app.get('/live')
    async def live():
        return {'alive':True}

    @app.get('/ready')
    async def ready(request: Request):
        return JSONResponse({'ready':request.app.state.accepting},
            status_code=200 if request.app.state.accepting else 503)

    @app.get('/local')
    async def local():
        return {'local':'ok'}

    @app.get('/orders/ord_42')
    async def order(request: Request):
        if not request.app.state.accepting:
            return JSONResponse({'code':'DRAINING'},status_code=503)
        try:
            return await request.app.state.caller.request_json('GET','/orders/ord_42',total_timeout=.5)
        except AdmissionTimeout:
            return JSONResponse({'code':'LOCAL_OVERLOAD'},status_code=503,headers={'Retry-After':'1'})
        except (AttemptDeadlineExceeded, TotalDeadlineExceeded):
            return JSONResponse({'code':'DEPENDENCY_DEADLINE'},status_code=504)
        except (ProviderFailure, httpx.HTTPError):
            return JSONResponse({'code':'DEPENDENCY_UNAVAILABLE'},status_code=502)

    return app

app = create_app()
