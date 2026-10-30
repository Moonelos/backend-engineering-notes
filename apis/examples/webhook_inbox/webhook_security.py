import base64
import binascii
import hashlib
import hmac
import time
from collections.abc import Iterable


class VerificationError(ValueError):
    """The webhook authentication data is missing, stale, or invalid."""


def _signed_content(*, body: bytes, message_id: str, timestamp: int) -> bytes:
    if not message_id or len(message_id) > 200 or "." in message_id:
        raise VerificationError("Invalid message identifier")
    return (
        message_id.encode("utf-8")
        + b"."
        + str(timestamp).encode("ascii")
        + b"."
        + body
    )


def sign_webhook(
    *,
    body: bytes,
    message_id: str,
    timestamp: int,
    secrets: Iterable[bytes],
) -> str:
    content = _signed_content(
        body=body,
        message_id=message_id,
        timestamp=timestamp,
    )
    signatures: list[str] = []
    for secret in secrets:
        if len(secret) < 24:
            raise ValueError("Webhook secrets must contain at least 192 bits")
        digest = hmac.new(secret, content, hashlib.sha256).digest()
        signatures.append(f"v1,{base64.b64encode(digest).decode('ascii')}")
    if not signatures:
        raise ValueError("At least one signing secret is required")
    return " ".join(signatures)


def verify_webhook(
    *,
    body: bytes,
    message_id: str | None,
    timestamp: str | None,
    signature_header: str | None,
    secrets: Iterable[bytes],
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    if message_id is None or timestamp is None or signature_header is None:
        raise VerificationError("Missing webhook authentication header")
    if len(signature_header) > 4096:
        raise VerificationError("Signature header is too large")

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise VerificationError("Invalid timestamp") from exc

    current_time = int(time.time()) if now is None else now
    if tolerance_seconds <= 0:
        raise ValueError("A positive replay tolerance is required")
    if abs(current_time - timestamp_value) > tolerance_seconds:
        raise VerificationError("Webhook timestamp is outside the allowed window")

    content = _signed_content(
        body=body,
        message_id=message_id,
        timestamp=timestamp_value,
    )
    supplied = [
        item.removeprefix("v1,")
        for item in signature_header.split()
        if item.startswith("v1,")
    ]
    if not supplied or len(supplied) > 10:
        raise VerificationError("No supported signature")

    # Compare decoded MAC bytes; malformed Unicode/base64 is an authentication failure.
    candidates = []
    for value in supplied:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            continue  # A malformed rotation candidate cannot authenticate the request.
        if len(decoded) == hashlib.sha256().digest_size:
            candidates.append(decoded)
    if not candidates:
        raise VerificationError("Malformed webhook signature")

    matched = False
    for secret in secrets:
        if len(secret) < 24:
            raise ValueError("Webhook secrets must contain at least 192 bits")
        expected = hmac.new(secret, content, hashlib.sha256).digest()
        for candidate in candidates:
            matched |= hmac.compare_digest(candidate, expected)

    if not matched:
        raise VerificationError("Invalid webhook signature")
