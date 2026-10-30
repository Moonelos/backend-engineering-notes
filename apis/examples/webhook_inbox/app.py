import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import asyncpg
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .webhook_security import VerificationError, verify_webhook


MAX_WEBHOOK_BYTES = 256 * 1024
SIGNING_SECRETS = [
    secret.encode("utf-8")
    for secret in os.environ["BILLING_WEBHOOK_SECRETS"].split(",")
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=200)
    schema_version: int = Field(ge=1)
    occurred_at: datetime
    producer: str
    data: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=1,
        max_size=10,
        command_timeout=5.0,
    )
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.post("/webhooks/billing", status_code=204)
async def receive_billing_webhook(request: Request) -> Response:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > MAX_WEBHOOK_BYTES:
                return Response(status_code=413)
        except ValueError:
            return Response(status_code=400)

    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > MAX_WEBHOOK_BYTES:
            return Response(status_code=413)
        chunks.append(chunk)
    raw_body = b"".join(chunks)

    message_id = request.headers.get("webhook-id")
    timestamp = request.headers.get("webhook-timestamp")
    signature = request.headers.get("webhook-signature")

    try:
        verify_webhook(
            body=raw_body,
            message_id=message_id,
            timestamp=timestamp,
            signature_header=signature,
            secrets=SIGNING_SECRETS,
        )
    except VerificationError:
        return Response(status_code=401)

    try:
        event = EventEnvelope.model_validate_json(raw_body)
    except ValidationError:
        return Response(status_code=422)

    if event.id != message_id or event.producer != "billing":
        return Response(status_code=400)

    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    async with request.app.state.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO webhook_inbox (
                producer, event_id, event_type, occurred_at, payload
            ) VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (producer, event_id) DO NOTHING
            """,
            event.producer,
            event.id,
            event.type,
            event.occurred_at,
            payload,
        )

    return Response(status_code=204)
