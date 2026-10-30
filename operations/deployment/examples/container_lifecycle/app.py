"""Loopback-only teaching app; marker files inject probe failures inside the container."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Response


@asynccontextmanager
async def lifespan(app):
    print("startup complete", flush=True)
    try:
        yield
    finally:
        # Real applications close resources in reverse acquisition order here.
        print("cleanup complete", flush=True)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health(response: Response):
    if Path("/tmp/fail-health").exists():
        response.status_code = 503
    return {"probe": "health"}


@app.get("/ready")
async def ready(response: Response):
    if Path("/tmp/fail-ready").exists():
        response.status_code = 503
    return {"probe": "ready"}


@app.get("/slow")
async def slow(seconds: Annotated[float, Query(ge=0, le=5)] = 3):
    print("slow request started", flush=True)
    await asyncio.sleep(seconds)
    return {"state": "complete"}
