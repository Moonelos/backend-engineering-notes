"""Python 3.11+; one owner for bounded local JSON requests. No real provider required."""
import asyncio
import json
import math
import random
import time
import uuid
from contextlib import asynccontextmanager, AsyncExitStack
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Callable

import httpx


class AdmissionTimeout(Exception):
    """Local/shared capacity unavailable; no local retry."""

class AttemptDeadlineExceeded(Exception):
    """An admitted attempt exceeded its cancellation deadline."""

class TotalDeadlineExceeded(Exception):
    """The logical operation exhausted its remaining budget."""

class ProviderFailure(Exception):
    def __init__(self, status: int | None = None, retry_after: str | None = None):
        self.status, self.retry_after = status, retry_after
        super().__init__(f"Provider failure: {status}" if status else "Invalid provider response")


class AdmissionGate:
    """Bound executing owners AND waiting callers, within one event loop/process."""
    def __init__(self, capacity: int, max_waiters: int):
        if capacity < 1 or max_waiters < 0:
            raise ValueError('Invalid admission capacity')
        self.capacity, self.max_waiters = capacity, max_waiters
        self.active = self.waiting = 0
        self._changed = asyncio.Condition()

    async def acquire(self):
        async with self._changed:
            if self.active >= self.capacity:
                if self.waiting >= self.max_waiters:
                    raise AdmissionTimeout('Local waiting capacity exhausted')
                self.waiting += 1
                try:
                    await self._changed.wait_for(lambda: self.active < self.capacity)
                finally:
                    self.waiting -= 1
            self.active += 1

    async def release(self):
        async with self._changed:
            if self.active < 1:
                raise RuntimeError('Permit released without ownership')
            self.active -= 1
            self._changed.notify(1)


class StartSpacing:
    """Optional process-local start spacing, without a token-bucket burst."""
    def __init__(self, starts_per_second: float):
        if not math.isfinite(starts_per_second) or starts_per_second <= 0:
            raise ValueError('Rate must be finite and positive')
        self.interval = 1 / starts_per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, self._next - loop.time()))
            self._next = loop.time() + self.interval


def retry_after_seconds(value: str | None, *, now: float | None = None) -> float | None:
    if value is None or len(value) > 128:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdigit():
            return float(int(value))
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, date.timestamp() - (time.time() if now is None else now))
    except (ValueError, TypeError, OverflowError):
        return None


@asynccontextmanager
async def local_only_attempt(operation_id: str, attempt_no: int):
    yield


class BoundedCaller:
    """The client and this caller are application-lifespan resources, not per-request objects.

    attempt_admission(operation_id, attempt_no) optionally owns an external attempt lease;
    its context covers the request and response close. It must classify denial as
    AdmissionTimeout and reconcile ambiguous admission using the stable attempt identity.
    """
    RETRY_STATUS = {408, 429, 502, 503, 504}

    def __init__(self, client: httpx.AsyncClient, *, capacity=20, max_waiters=40,
                 admission_timeout=1.0, attempt_timeout=2.0, max_response_bytes=262144,
                 rate: StartSpacing | None = None, attempt_admission=local_only_attempt,
                 jitter: Callable[[int], float] | None = None):
        if any(not math.isfinite(v) or v <= 0 for v in (admission_timeout, attempt_timeout)):
            raise ValueError('Timeouts must be finite and positive')
        if max_response_bytes < 1:
            raise ValueError('Response byte bound must be positive')
        self.client = client
        self.gate = AdmissionGate(capacity, max_waiters)
        self.admission_timeout, self.attempt_timeout = admission_timeout, attempt_timeout
        self.max_response_bytes = max_response_bytes
        self.rate, self.attempt_admission = rate, attempt_admission
        self.jitter = jitter or (lambda n: random.uniform(0, min(.1 * 2**n, 1.0)))
        self.attempts_started = 0

    @asynccontextmanager
    async def _admit(self, operation_id, attempt):
        acquired = False
        try:
            async with AsyncExitStack() as owned:
                try:
                    async with asyncio.timeout(self.admission_timeout):
                        await self.gate.acquire()
                        acquired = True
                        if self.rate:
                            await self.rate.acquire()
                        await owned.enter_async_context(self.attempt_admission(operation_id, attempt))
                except TimeoutError as exc:
                    raise AdmissionTimeout('Admission deadline') from exc
                # The admission timer has exited; the response lifetime starts now.
                yield
        finally:
            if acquired:
                await self.gate.release()

    async def _send(self, method, path, payload, headers):
        headers = {**headers, 'Accept-Encoding': 'identity'}
        async with self.client.stream(method, path, json=payload, headers=headers) as response:
            if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ProviderFailure()  # Do not inflate an unbounded compressed body in this lab.
            if response.status_code >= 400:
                raise ProviderFailure(response.status_code, response.headers.get('Retry-After'))
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise ProviderFailure()
            try:
                result = json.loads(body)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ProviderFailure() from exc
            if not isinstance(result, dict):
                raise ProviderFailure()
            return result

    async def request_json(self, method: str, path: str, *, payload=None,
                           total_timeout=5.0, max_attempts=3,
                           idempotency_key: str | None = None,
                           provider_deduplicates: bool = False,
                           operation_id: str | None = None):
        if not math.isfinite(total_timeout) or total_timeout <= 0 or max_attempts < 1:
            raise ValueError('Invalid operation budget')
        method = method.upper()
        retry_safe = method == 'GET' or (provider_deduplicates and bool(idempotency_key))
        operation_id = operation_id or str(uuid.uuid4())
        headers = {'Idempotency-Key': idempotency_key} if idempotency_key else {}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + total_timeout
        total_scope = asyncio.timeout_at(deadline)
        try:
            async with total_scope:
                for attempt in range(max_attempts):
                    error = None
                    try:
                        async with self._admit(operation_id, attempt):
                            try:
                                async with asyncio.timeout(self.attempt_timeout):
                                    self.attempts_started += 1
                                    return await self._send(method, path, payload, headers)
                            except TimeoutError as exc:
                                raise AttemptDeadlineExceeded() from exc
                    except httpx.PoolTimeout as exc:
                        raise AdmissionTimeout('Transport pool exhausted') from exc
                    except ProviderFailure as exc:
                        if exc.status not in self.RETRY_STATUS:
                            raise
                        error = exc
                    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError,
                            httpx.ReadTimeout, httpx.WriteError, httpx.WriteTimeout,
                            httpx.RemoteProtocolError, AttemptDeadlineExceeded) as exc:
                        error = exc

                    if not retry_safe or attempt == max_attempts - 1:
                        raise error
                    retry_after = retry_after_seconds(getattr(error, 'retry_after', None))
                    delay = max(self.jitter(attempt), retry_after or 0.0)
                    if delay >= deadline - loop.time():
                        raise TotalDeadlineExceeded('No time remains for a permitted retry')
                    await asyncio.sleep(delay)
        except TimeoutError as exc:
            if total_scope.expired():
                raise TotalDeadlineExceeded('Logical operation deadline') from exc
            raise
        raise RuntimeError('Unreachable')
