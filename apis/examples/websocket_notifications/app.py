import asyncio
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError


logger = logging.getLogger(__name__)
app = FastAPI()

SESSION_SECRET = os.environ["WS_SESSION_SECRET"].encode("utf-8")
if len(SESSION_SECRET) < 32:
    raise ValueError("Use a random session secret of at least 32 bytes")
SEND_TIMEOUT = 5.0
CLOSE_TIMEOUT = 1.0
ALLOWED_ORIGINS = {"https://app.example.com"}
SUBPROTOCOL = "notifications.v1"
MAX_INBOUND_BYTES = 16 * 1024
MAX_OUTBOUND_MESSAGES = 100


class ClientMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    type: Literal["app.ping", "notifications.subscribe"]
    message_id: str = Field(min_length=1, max_length=100)
    payload: dict[str, str] = Field(default_factory=dict)


def sign_session(user_id: str, expires_at: int) -> str:
    if "." in user_id:
        raise ValueError("user_id must not contain a dot")
    value = f"{user_id}.{expires_at}"
    signature = hmac.new(
        SESSION_SECRET,
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{value}.{signature}"


def verify_session(token: str | None) -> str | None:
    if token is None or len(token) > 1024:
        return None
    try:
        user_id, expires_text, supplied_signature = token.split(".", maxsplit=2)
        expires_at = int(expires_text)
    except (ValueError, TypeError):
        return None

    signed_value = f"{user_id}.{expires_at}"
    expected_signature = hmac.new(
        SESSION_SECRET,
        signed_value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    try:
        supplied_bytes = bytes.fromhex(supplied_signature)
    except ValueError:
        return None
    if len(supplied_signature) != 64 or not user_id:
        return None
    if not hmac.compare_digest(supplied_bytes, bytes.fromhex(expected_signature)):
        return None
    if expires_at <= int(time.time()):
        return None
    return user_id


@dataclass(eq=False)
class CloseInstruction:
    code: int
    reason: str


@dataclass(eq=False)
class ClientConnection:
    websocket: WebSocket
    user_id: str
    outbound: asyncio.Queue[dict[str, object] | CloseInstruction] = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_OUTBOUND_MESSAGES)
    )
    subscribed: bool = False
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    close_code: int = 1000
    close_reason: str = "connection finished"


class ConnectionHub:
    def __init__(self) -> None:
        self._clients: set[ClientConnection] = set()
        self._lock = asyncio.Lock()

    async def add(self, client: ClientConnection) -> None:
        async with self._lock:
            self._clients.add(client)

    async def remove(self, client: ClientConnection) -> None:
        async with self._lock:
            self._clients.discard(client)

    async def publish_to_user(
        self,
        user_id: str,
        message: dict[str, object],
    ) -> None:
        async with self._lock:
            recipients = [
                client
                for client in self._clients
                if client.user_id == user_id and client.subscribed
            ]

        for client in recipients:
            try:
                client.outbound.put_nowait(message)
            except asyncio.QueueFull:
                # The event must also be recoverable from durable state.
                client.close_code = 1013
                client.close_reason = "slow consumer"
                client.stop.set()  # Independent of the full queue and blocked send.


hub = ConnectionHub()


async def send_messages(client: ClientConnection) -> None:
    while True:
        item = await client.outbound.get()
        if isinstance(item, CloseInstruction):
            client.close_code, client.close_reason = item.code, item.reason
            client.stop.set()
            return
        try:
            async with asyncio.timeout(SEND_TIMEOUT):
                await client.websocket.send_json(item)
        except TimeoutError:
            client.close_code, client.close_reason = 1013, "send deadline"
            client.stop.set()
            return


async def receive_messages(client: ClientConnection) -> None:
    while True:
        # Defense in depth only: receive_text() has already caused the backend
        # to buffer, assemble, decompress, and decode the message.
        raw_message = await client.websocket.receive_text()
        if len(raw_message.encode("utf-8")) > MAX_INBOUND_BYTES:
            client.close_code, client.close_reason = 1009, "message too large"
            client.stop.set()
            return

        try:
            message = ClientMessage.model_validate_json(raw_message)
        except ValidationError:
            await client.outbound.put(
                {
                    "version": 1,
                    "type": "error",
                    "payload": {
                        "code": "INVALID_MESSAGE",
                        "message": "Message does not match the protocol schema.",
                        "retryable": False,
                    },
                }
            )
            continue

        if message.type == "app.ping":
            await client.outbound.put(
                {
                    "version": 1,
                    "type": "app.pong",
                    "request_id": message.message_id,
                    "payload": {},
                }
            )
        elif message.type == "notifications.subscribe":
            client.subscribed = True
            await client.outbound.put(
                {
                    "version": 1,
                    "type": "notifications.subscribed",
                    "request_id": message.message_id,
                    "payload": {},
                }
            )


@app.websocket("/ws/notifications")
async def notifications_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="origin not allowed")
        return

    if SUBPROTOCOL not in websocket.scope.get("subprotocols", []):
        await websocket.close(code=1002, reason="subprotocol required")
        return

    user_id = verify_session(websocket.cookies.get("session"))
    if user_id is None:
        await websocket.close(code=1008, reason="authentication required")
        return

    await websocket.accept(subprotocol=SUBPROTOCOL)
    client = ClientConnection(websocket=websocket, user_id=user_id)
    await hub.add(client)

    sender = asyncio.create_task(send_messages(client), name=f"ws-send-{user_id}")
    receiver = asyncio.create_task(receive_messages(client), name=f"ws-receive-{user_id}")

    stopper = asyncio.create_task(client.stop.wait(), name=f"ws-stop-{user_id}")
    try:
        done, pending = await asyncio.wait(
            {sender, receiver, stopper},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            if task.cancelled():
                continue
            error = task.exception()
            if error is not None and not isinstance(error, WebSocketDisconnect):
                logger.error(
                    "websocket_task_failed",
                    extra={"user_id": user_id, "error_type": type(error).__name__},
                )
    finally:
        sender.cancel()
        receiver.cancel()
        stopper.cancel()
        await asyncio.gather(sender, receiver, stopper, return_exceptions=True)
        await hub.remove(client)
        # The supervisor closes only after the sender has stopped.
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT):
                await websocket.close(code=client.close_code, reason=client.close_reason)
        except (TimeoutError, RuntimeError, WebSocketDisconnect):
            pass  # Already disconnected or the bounded close could not be delivered.
