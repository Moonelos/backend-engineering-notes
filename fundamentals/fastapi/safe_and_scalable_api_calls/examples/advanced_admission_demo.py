"""Two provider attempts, two RPM entries, zero live leases afterward."""
import asyncio
import uuid
import httpx
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from advanced_admission import FleetAdmission
from bounded_calls import BoundedCaller

async def main():
    calls=0
    async def provider(request):
        nonlocal calls
        calls+=1
        return httpx.Response(503 if calls==1 else 200,json={'ok':True})
    async with Redis.from_url('redis://localhost:57379/0',decode_responses=True,
            socket_connect_timeout=.2,socket_timeout=.2,retry=Retry(NoBackoff(),0)) as redis:
        fleet=FleetAdmission(redis,account=uuid.uuid4().hex,user='verified-tenant',
                             attempt_ms=2000,lease_ms=5000)
        async with httpx.AsyncClient(base_url='https://fixture.invalid',
                transport=httpx.MockTransport(provider)) as client:
            caller=BoundedCaller(client,attempt_timeout=2,attempt_admission=fleet.attempt,jitter=lambda n:0)
            result=await caller.request_json('GET','/',operation_id='inventory-q1',max_attempts=2)
        print(result,'provider_attempts=',calls,'rpm_entries=',await redis.zcard(fleet.rpm_key),
              'active=',await redis.zcard(fleet.global_key))
        assert calls==await redis.zcard(fleet.rpm_key)==2
        assert await redis.zcard(fleet.global_key)==0

if __name__=='__main__':
    asyncio.run(main())
