import asyncio
import os
import uuid
import httpx
import pytest
from redis.asyncio import Redis
from advanced_admission import FleetAdmission
from advanced_resilience import SharedBreaker
from bounded_calls import AdmissionTimeout, BoundedCaller

URL = os.environ.get('ADVANCED_REDIS_URL', 'redis://localhost:57379/0')


def test_final_permit_race_recovery_pause_and_script_reload():
    async def run():
        async with Redis.from_url(URL, decode_responses=True, socket_timeout=.2) as a, \
                Redis.from_url(URL, decode_responses=True, socket_timeout=.2) as b:
            account = uuid.uuid4().hex
            first = FleetAdmission(a, account=account, global_limit=1, lease_ms=100, attempt_ms=20)
            second = FleetAdmission(b, account=account, global_limit=1, lease_ms=100, attempt_ms=20)
            results = await asyncio.gather(first.acquire('a', 0, 'owner-a'), second.acquire('b', 0, 'owner-b'))
            assert sum(int(r[0]) for r in results) == 1
            winner, operation, owner = (first, 'a', 'owner-a') if int(results[0][0]) else (second, 'b', 'owner-b')
            # Simulate losing the committed reply: recover with same identity/owner.
            assert int((await winner.acquire(operation, 0, owner))[0]) == 1
            assert await a.zcard(first.rpm_key) == 1
            assert int((await winner.acquire(operation, 0, 'competing-process'))[0]) == 0
            await a.script_flush()
            await winner.release(operation, 0, owner)  # register_script reloads NOSCRIPT.
            assert await a.zcard(first.global_key) == 0
            await a.hset(first.flags_key, 'paused', '1')
            assert (await first.acquire('paused', 0, 'p'))[1] == 'paused'
            await a.hset(first.flags_key, 'paused', '0')
            await first.acquire('old', 0, 'old-owner')
            await asyncio.sleep(.12)
            assert int((await second.acquire('new', 0, 'new-owner'))[0]) == 1
            await first.release('old', 0, 'old-owner')
            assert await a.zscore(first.global_key, 'new-owner') is not None
            await second.release('new', 0, 'new-owner')
    asyncio.run(run())


def test_user_limit_rpm_and_bounded_caller_hook():
    async def run():
        async with Redis.from_url(URL, decode_responses=True, socket_timeout=.2) as redis:
            fleet = FleetAdmission(redis, account=uuid.uuid4().hex, global_limit=3, user_limit=1, rpm=2)
            await fleet.acquire('held', 0, 'held')
            assert (await fleet.acquire('blocked', 0, 'blocked'))[1] == 'user_concurrency'
            await fleet.release('held', 0, 'held')
            calls = 0
            async def handler(request):
                nonlocal calls
                calls += 1
                return httpx.Response(503 if calls == 1 else 200, json={'ok': True})
            async with httpx.AsyncClient(base_url='https://test', transport=httpx.MockTransport(handler)) as client:
                caller = BoundedCaller(client, attempt_admission=fleet.attempt, jitter=lambda n: 0)
                with pytest.raises(AdmissionTimeout):
                    await caller.request_json('GET', '/', operation_id='request')
                # Prior held attempt + first provider attempt consume RPM. Retry is denied.
                assert calls == 1 and caller.gate.active == 0
                assert await redis.zcard(fleet.global_key) == 0
    asyncio.run(run())


def test_probe_generation_and_late_success():
    async def run():
        async with Redis.from_url(URL, decode_responses=True) as redis:
            breaker = SharedBreaker(redis, 'breaker:' + uuid.uuid4().hex,
                                    threshold=1, cooldown_ms=10, probe_ms=30)
            ticket = await breaker.allow()
            await breaker.record(ticket, 'failure')
            with pytest.raises(AdmissionTimeout):
                await breaker.allow()
            await asyncio.sleep(.015)
            old = await breaker.allow()
            await asyncio.sleep(.04)
            new = await breaker.allow()
            assert not await breaker.record(old, 'success')
            assert await redis.hget(breaker.key, 'token') == new[1]
            assert await breaker.record(new, 'failure')
            assert not await breaker.record(old, 'success')
            assert await redis.hget(breaker.key, 'state') == 'open'
    asyncio.run(run())


def test_committed_reply_lost_and_cancelled_acquisition_cleanup():
    async def run():
        from redis.exceptions import ConnectionError
        async with Redis.from_url(URL, decode_responses=True, socket_timeout=.2) as redis:
            fleet=FleetAdmission(redis,account=uuid.uuid4().hex)
            real_acquire=fleet.acquire
            calls=0
            async def reply_lost(operation, attempt, owner):
                nonlocal calls
                calls+=1
                result=await real_acquire(operation,attempt,owner)
                if calls==1:
                    raise ConnectionError('Injected lost committed response')
                return result
            fleet.acquire=reply_lost
            async with fleet.attempt('lost',0):
                assert await redis.zcard(fleet.global_key)==1
            assert calls==2 and await redis.zcard(fleet.rpm_key)==1
            committed=asyncio.Event()
            async def committed_then_wait(operation,attempt,owner):
                await real_acquire(operation,attempt,owner)
                committed.set()
                await asyncio.sleep(10)
            fleet.acquire=committed_then_wait
            async def enter():
                async with fleet.attempt('cancelled',0):
                    pytest.fail('Must not dispatch')
            task=asyncio.create_task(enter())
            await committed.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert await redis.zcard(fleet.global_key)==0
    asyncio.run(run())


def test_redis_unavailable_fails_closed_without_provider_send():
    async def run():
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff
        async with Redis.from_url('redis://127.0.0.1:1/0',socket_connect_timeout=.01,
                socket_timeout=.01,retry=Retry(NoBackoff(),0)) as redis:
            fleet=FleetAdmission(redis)
            called=False
            async def provider(request):
                nonlocal called
                called=True
                return httpx.Response(200,json={})
            async with httpx.AsyncClient(base_url='https://test',transport=httpx.MockTransport(provider)) as client:
                caller=BoundedCaller(client,attempt_admission=fleet.attempt)
                with pytest.raises(AdmissionTimeout): await caller.request_json('GET','/')
                assert not called and caller.gate.active==0
    asyncio.run(run())
