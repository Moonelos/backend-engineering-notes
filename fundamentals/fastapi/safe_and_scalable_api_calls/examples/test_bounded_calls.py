import asyncio
from contextlib import asynccontextmanager
from email.utils import formatdate

import httpx
import pytest
from bounded_calls import (AdmissionGate, BoundedCaller, AdmissionTimeout,
                           TotalDeadlineExceeded, ProviderFailure, retry_after_seconds)


def run_case(fn):
    asyncio.run(fn())


def test_invalid_json_maps_to_provider_failure():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b'{"x":')),
                base_url='https://test') as client:
            caller = BoundedCaller(client)
            with pytest.raises(ProviderFailure):
                await caller.request_json('GET', '/')
            assert caller.attempts_started == 1 and caller.gate.active == 0
    run_case(scenario)


def test_admission_scope_ends_before_execution():
    async def scenario():
        async def provider(request):
            await asyncio.sleep(.05)
            return httpx.Response(200, json={'ok': True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url='https://test') as client:
            caller = BoundedCaller(client, admission_timeout=.01, attempt_timeout=.2)
            assert await caller.request_json('GET','/') == {'ok': True}
            assert caller.gate.active == 0
    run_case(scenario)


def test_waiting_count_and_cancellation():
    async def scenario():
        gate = AdmissionGate(1, 1)
        await gate.acquire()
        task = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0)
        assert gate.waiting == 1
        with pytest.raises(AdmissionTimeout):
            await gate.acquire()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gate.waiting == 0 and gate.active == 1
        await gate.release()
        assert gate.active == 0
    run_case(scenario)


def test_retry_releases_resources_and_preserves_operation_key():
    async def scenario():
        headers, entries, active_at_sleep = [], [], []
        @asynccontextmanager
        async def external(operation_id, attempt):
            entries.append((operation_id, attempt, 'enter'))
            try:
                yield
            finally:
                entries.append((operation_id, attempt, 'exit'))
        async def provider(request):
            headers.append(request.headers['Idempotency-Key'])
            return httpx.Response(503 if len(headers)==1 else 200, json={'ok': True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url='https://test') as client:
            def jitter(attempt):
                active_at_sleep.append(caller.gate.active)
                return 0
            caller = BoundedCaller(client, attempt_admission=external, jitter=jitter)
            assert await caller.request_json('POST','/', payload={}, idempotency_key='tenant7:op42',
                provider_deduplicates=True, operation_id='op42') == {'ok': True}
            assert headers == ['tenant7:op42', 'tenant7:op42']
            assert active_at_sleep == [0]
            assert entries == [('op42',0,'enter'),('op42',0,'exit'),('op42',1,'enter'),('op42',1,'exit')]
    run_case(scenario)


def test_pool_timeout_and_unsafe_post_do_not_retry():
    async def scenario():
        async def pool_full(request):
            raise httpx.PoolTimeout('local', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(pool_full), base_url='https://test') as client:
            caller = BoundedCaller(client)
            with pytest.raises(AdmissionTimeout):
                await caller.request_json('GET','/')
            assert caller.attempts_started == 1 and caller.gate.active == 0
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)), base_url='https://test') as client:
            caller = BoundedCaller(client)
            with pytest.raises(ProviderFailure):
                await caller.request_json('POST','/',payload={})
            assert caller.attempts_started == 1
    run_case(scenario)


def test_total_deadline_closes_trickling_body():
    class Trickle(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            for chunk in [b'{', b'"ok"', b':', b'true', b'}']:
                await asyncio.sleep(.025)
                yield chunk
        async def aclose(self):
            self.closed = True
    async def scenario():
        stream = Trickle()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)), base_url='https://test') as client:
            caller = BoundedCaller(client, attempt_timeout=1)
            with pytest.raises(TotalDeadlineExceeded):
                await caller.request_json('GET','/',total_timeout=.04)
            assert stream.closed and caller.gate.active == 0
    run_case(scenario)


def test_cancelled_attempt_is_joined_and_released():
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        async def provider(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url='https://test') as client:
            caller = BoundedCaller(client)
            task = asyncio.create_task(caller.request_json('GET','/'))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stopped.is_set() and caller.gate.active == 0
    run_case(scenario)


def test_retry_after_seconds_and_date():
    assert retry_after_seconds('2', now=0) == 2
    assert retry_after_seconds(formatdate(100, usegmt=True), now=90) == 10
    assert retry_after_seconds('not a date') is None


def test_external_admission_timeout_releases_local_permit():
    async def scenario():
        @asynccontextmanager
        async def never_admit(operation_id, attempt):
            await asyncio.Event().wait()
            yield
        async with httpx.AsyncClient(base_url='https://test') as client:
            caller = BoundedCaller(client, admission_timeout=.01, attempt_admission=never_admit)
            with pytest.raises(AdmissionTimeout):
                await caller.request_json('GET','/')
            assert caller.attempts_started == 0 and caller.gate.active == 0
    run_case(scenario)
