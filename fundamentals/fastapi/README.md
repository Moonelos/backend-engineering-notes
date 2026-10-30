# FastAPI Guides

> Production-ready patterns and best practices for FastAPI applications.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://pydantic.dev)
[![Starlette](https://img.shields.io/badge/Starlette-0.40+-009688.svg)](https://www.starlette.io)

---

## Quick start: one route and one owned HTTP client

This self-contained service owns an `httpx.AsyncClient` for the application's lifetime and calls a
local in-process provider, so it needs no network or credentials.

Install `fastapi`, `httpx`, and `asgi-lifespan`, save this as `app.py`, then run `python app.py`:

```python
import asyncio
from contextlib import asynccontextmanager

import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI, Request


provider = FastAPI()


@provider.get("/status")
async def provider_status() -> dict[str, str]:
    return {"provider": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=provider),
        base_url="http://provider.test",
        timeout=httpx.Timeout(2.0),
    )
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/provider-status")
async def read_provider_status(request: Request) -> dict[str, str]:
    response = await request.app.state.http.get("/status")
    response.raise_for_status()
    return response.json()


async def main() -> None:
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://service.test"
        ) as client:
            response = await client.get("/provider-status")
            print(response.status_code, response.json())


if __name__ == "__main__":
    asyncio.run(main())
```

The success signal is exactly:

```text
200 {'provider': 'ok'}
```

If startup ownership is missing, the common tell is `AttributeError: 'State' object has no
attribute 'http'`; constructing a client per request instead hides the error but defeats pooling.

> **Production:** The local transport deliberately removes DNS, TLS, and provider failure. Keep the
> lifetime pattern, then add bounded admission, separate total and transport deadlines, eligible
> retries, and observability through [Safe and Scalable API Calls](safe_and_scalable_api_calls/README.md).

---

## Contents

### Core Guides

| Part | Topic | Description |
|------|-------|-------------|
| [01](01_http_and_parameter_mapping.md) | HTTP & Parameter Mapping | HTTP request structure, FastAPI's parameter resolution rules |
| [02](02_dependency_injection.md) | Dependency Injection | `Depends` mental model, patterns, testing |
| [03](03_pydantic.md) | Pydantic at HTTP boundaries | Request/response models, validation errors and partial updates; general mechanics live in [Core Pydantic](../core_concepts/data_models/pydantic/README.md) |
| [04](04_authentication.md) | Authentication & Security | JWT, OAuth2, CORS, password hashing, security headers |
| [05](05_middleware.md) | Middleware | Request ID, timing, CORS, error handling, ordering |
| [06](06_websockets.md) | WebSockets | Connections, rooms, auth, heartbeat, scaling |
| [07](07_error_handling.md) | Error Responses | Exception hierarchy, global handlers, consistent shapes |
| [08](08_streaming.md) | Streaming | StreamingResponse, SSE, file downloads, backpressure |
| [09](09_background_tasks_and_routers.md) | BackgroundTasks & APIRouter | Fire-and-forget after response, app structure, OpenAPI customization |
| [10](10_api_design.md) | API Design Conventions | REST shape, methods, pagination, versioning, OpenAPI hygiene |
| [11](11_api_security.md) | API Security | Object/function/property authorization, abuse controls, SSRF, webhooks, uploads, auditability |
| [12](12_file_uploads_and_object_storage.md) | File uploads and object storage | Bound bytes, quarantine objects, verify content and authorize downloads |

### External API Calls

- **[Safe and Scalable API Calls](safe_and_scalable_api_calls/README.md)** — Production guide for calling LLMs and external services

  | Part | Topic | Description |
  |------|-------|-------------|
  | [01](safe_and_scalable_api_calls/01_core_concepts.md) | Core Concepts | Mental model, the real concurrency limit |
  | [02](safe_and_scalable_api_calls/02_concurrency_and_timeouts.md) | Concurrency & Timeouts | Timeout layers, asyncio vs httpx |
  | [03](safe_and_scalable_api_calls/03_call_patterns.md) | Call Patterns | Gold standard pattern, retry logic |
  | [04](safe_and_scalable_api_calls/04_kubernetes.md) | Kubernetes | Multi-pod concerns, local vs global |
  | [05](safe_and_scalable_api_calls/05_production_architecture.md) | Production Architecture | Complete stack, execution order |
  | [06](safe_and_scalable_api_calls/06_advanced_patterns.md) | Advanced Patterns | Circuit breakers, bulkheads, hedging, priority queues |
  | [07](safe_and_scalable_api_calls/07_streaming_patterns.md) | Streaming Patterns | SSE, streaming timeouts |
  | [08](safe_and_scalable_api_calls/08_streaming_advanced.md) | Streaming Advanced | Multi-stream, aggregation |
  | [09](safe_and_scalable_api_calls/09_distributed_admission_control.md) | Distributed Admission Control | Redis-centric admission, atomic Lua, retries & quota accounting |
  | [10](safe_and_scalable_api_calls/10_llm_token_economics.md) | LLM Token Economics | Reserve → Retry → Reconcile, cost observability, retry budgets |
  | [11](safe_and_scalable_api_calls/11_idempotency.md) | Idempotency Keys | Safe POST retries, dedup state machine, Postgres + Redis backends |

---

## Integration continuation

For signed inbound events and outbound delivery, follow the existing [webhook course](../../apis/webhooks/README.md). It owns signature verification, replay protection, inbox/outbox, retry schedules, delivery logs and CI fixtures; a second FastAPI-specific webhook chapter would duplicate that path.

## Prerequisites

**[API Communication Guides](../../apis/README.md)** — protocol-neutral foundations, style selection, REST, WebSockets, and webhooks

**[HTTPX Guide](../httpx/README.md)** — connection pooling, timeouts, HTTP client internals (required before Safe API Calls)

---

## Architecture Layers

```
API Gateway → ASGI Server → FastAPI → HTTP Client → Vendor
     ↓             ↓           ↓           ↓
  Flood       Admission    Business    Transport
 Protection    Control      Logic      Timeouts
```

---

## Reading Path

**Working result by entry 1**: run the quick start above and observe the provider response.

1. **Do:** run the [quick start](#quick-start-one-route-and-one-owned-http-client).
2. **Understand:** [HTTPX Guide](../httpx/README.md) — trace client, pool, transport, and timeout behavior.
3. **Harden:** [Safe API Calls](safe_and_scalable_api_calls/README.md) — add admission, retry classification, shared limits, and operations.

**Stop here if** one owned client with a bounded call meets the service's dependency contract.
Continue when concurrency, retries, streaming, multiple pods, or provider quota becomes relevant.
