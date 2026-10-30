"""Run: uvicorn advanced_stream_app:app --port 8087 (local fake provider)."""
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Header, HTTPException
from advanced_streaming import FiniteSSE, WeightedGate, demo_transport

streams, stats = [], {}
gate = WeightedGate(4, max_waiters=4)

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(base_url='https://fixture.invalid',
            transport=demo_transport(streams), timeout=httpx.Timeout(5)) as client:
        app.state.client = client
        yield

app = FastAPI(lifespan=lifespan)

@app.get('/events')
async def events(authorization: str = Header(default='')):
    # Lab credential only; production dependency resolves tenant/tier from verified identity.
    if authorization != 'Bearer local-demo':
        raise HTTPException(401, 'Authentication required')
    return FiniteSSE(app.state.client, gate, stats=stats)

@app.get('/metrics')
async def metrics(authorization: str = Header(default='')):
    if authorization != 'Bearer local-demo':
        raise HTTPException(401, 'Authentication required')
    return {'active_units': gate.used, 'waiting': gate.waiting, 'outcomes': stats}
