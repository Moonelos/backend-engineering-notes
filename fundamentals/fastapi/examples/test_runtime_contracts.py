"""Observed framework boundaries used by the repaired FastAPI lessons."""
import asyncio
from typing import Annotated

import pytest
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, model_validator
from starlette.middleware.base import BaseHTTPMiddleware


def test_path_binding_and_strict_json_content_type():
    app = FastAPI()
    class Payload(BaseModel):
        name: str
    @app.post('/items/{item_id}')
    def endpoint(payload: Payload, item_id: int = 5):
        return {'id': item_id, 'name': payload.name}
    with TestClient(app) as client:
        assert client.post('/items/7?item_id=9', json={'name': 'x'}).json()['id'] == 7
        assert client.post('/items/7', content=b'{"name":"x"}').status_code == 422
        assert client.post('/items/7', content=b'{"name":"x"}',
                           headers={'content-type': 'text/plain'}).status_code == 422
    with pytest.raises(AssertionError):
        @app.get('/bad/{item_id}')
        def bad(item_id: Annotated[int, Query()]): return item_id


def test_current_form_defaults_and_parameter_model_extra():
    app = FastAPI()
    @app.post('/checkbox')
    def checkbox(enabled: Annotated[bool, Form()] = False): return enabled
    @app.post('/required')
    def required(enabled: Annotated[bool, Form()]): return enabled
    class Filters(BaseModel):
        model_config = ConfigDict(extra='forbid')
        limit: int = 10
    def trace(trace: str = ''): return trace
    @app.get('/filters')
    def filters(filters: Annotated[Filters, Query()], trace_id=Depends(trace)):
        return filters.model_dump()
    with TestClient(app) as client:
        assert client.post('/checkbox', data={}).json() is False
        assert client.post('/required', data={}).status_code == 422
        assert client.get('/filters?limit=2').status_code == 200
        assert client.get('/filters?limit=2&trace=abc').status_code == 422
    with pytest.raises(TypeError): Query(custom='old-extension')
    assert Query(json_schema_extra={'custom': 'extension'}).json_schema_extra['custom'] == 'extension'


@pytest.mark.parametrize('scope,expected', [('function', ['open', 'endpoint', 'close', 'body']),
                                           ('request', ['open', 'endpoint', 'body', 'close'])])
def test_dependency_scope(scope, expected):
    app, trace = FastAPI(), []
    async def resource():
        trace.append('open')
        try: yield object()
        finally: trace.append('close')
    @app.get('/')
    async def endpoint(value=Depends(resource, scope=scope)):
        trace.append('endpoint')
        async def body():
            trace.append('body')
            yield b'ok'
        return StreamingResponse(body())
    with TestClient(app) as client: assert client.get('/').text == 'ok'
    assert trace == expected


def test_handler_specificity_headers_and_background_failure():
    app, trace = FastAPI(), []
    class NotFound(Exception): pass
    @app.exception_handler(Exception)
    async def generic(request, exc): return JSONResponse({'handler': 'generic'}, 500)
    @app.exception_handler(NotFound)
    async def specific(request, exc): return JSONResponse({'handler': 'specific'}, 404)
    @app.get('/missing')
    def missing(): raise NotFound()
    @app.get('/auth')
    def auth(): raise HTTPException(401, 'required', headers={'WWW-Authenticate': 'Bearer'})
    def first():
        trace.append('first')
        raise RuntimeError('background failed')
    def second(): trace.append('second')
    @app.get('/background')
    def background(tasks: BackgroundTasks):
        tasks.add_task(first)
        tasks.add_task(second)
        return {'accepted': True}
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get('/missing').json() == {'handler': 'specific'}
        assert client.get('/auth').headers['www-authenticate'] == 'Bearer'
        response = client.get('/background')
        assert response.status_code == 200 and response.json() == {'accepted': True}
        assert trace == ['first']


def test_base_http_middleware_forwards_before_producer_finishes():
    async def scenario():
        release, seen = asyncio.Event(), asyncio.Event()
        async def inner(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'A', 'more_body': True})
            await release.wait()
            await send({'type': 'http.response.body', 'body': b'B', 'more_body': False})
        async def dispatch(request, call_next): return await call_next(request)
        async def receive(): await asyncio.Event().wait()
        messages = []
        async def send(message):
            messages.append(message)
            if message.get('body') == b'A': seen.set()
        task = asyncio.create_task(BaseHTTPMiddleware(inner, dispatch=dispatch)(
            {'type': 'http', 'method': 'GET', 'path': '/', 'headers': [],
             'asgi': {'spec_version': '2.4'}}, receive, send))
        await asyncio.wait_for(seen.wait(), .5)
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, .5)
        assert b''.join(m.get('body', b'') for m in messages) == b'AB'
    asyncio.run(scenario())


def test_dispatch_can_change_headers_before_outgoing_start():
    app = FastAPI()
    @app.middleware('http')
    async def transform(request, call_next):
        response = await call_next(request)
        response.headers['X-Example'] = 'present'
        response.status_code = 202
        return response
    @app.get('/')
    def route(): return {'value': 1}
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 202 and response.headers['x-example'] == 'present'
        assert response.json() == {'value': 1}


def test_required_dependency_scalar_and_constructor_validation():
    app = FastAPI()
    class Even(BaseModel):
        value: int
        @model_validator(mode='after')
        def even(self):
            if self.value % 2:
                raise ValueError('must be even')
            return self
    @app.get('/')
    def route(value=Depends(Even)): return value.model_dump()
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get('/').status_code == 422
        assert client.get('/?value=2').json() == {'value': 2}
        assert client.get('/?value=odd').status_code == 422
        assert client.get('/?value=3').status_code == 500
