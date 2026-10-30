"""Redis 7+ attempt admission hook for bounded_calls.BoundedCaller."""
import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from redis.exceptions import RedisError
from bounded_calls import AdmissionTimeout
from advanced_streaming import finish

ADMIT = r'''
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+tonumber(t[2])/1000
local token=ARGV[1]; local ttl=tonumber(ARGV[2]); local minimum=tonumber(ARGV[3])
local previous=redis.call('HGET',KEYS[4],'state')
if previous then
  if previous=='granted' and redis.call('HGET',KEYS[4],'owner')==token and
      tonumber(redis.call('HGET',KEYS[4],'until'))-now>=minimum then return {1,'recovered'} end
  return {0,'previous_attempt'}
end
if redis.call('HGET',KEYS[5],'paused')=='1' then return {0,'paused'} end
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now)
redis.call('ZREMRANGEBYSCORE',KEYS[2],'-inf',now)
redis.call('ZREMRANGEBYSCORE',KEYS[3],'-inf',now-60000)
if redis.call('ZCARD',KEYS[1])>=tonumber(ARGV[4]) then return {0,'global_concurrency'} end
if redis.call('ZCARD',KEYS[2])>=tonumber(ARGV[5]) then return {0,'user_concurrency'} end
if redis.call('ZCARD',KEYS[3])>=tonumber(ARGV[6]) then return {0,'provider_rpm'} end
redis.call('ZADD',KEYS[1],now+ttl,token)
redis.call('ZADD',KEYS[2],now+ttl,token)
redis.call('ZADD',KEYS[3],now,token)
redis.call('HSET',KEYS[4],'state','granted','owner',token,'until',now+ttl)
redis.call('PEXPIRE',KEYS[4],86400000)
return {1,'new'}
'''
RELEASE = r'''
local owner=redis.call('HGET',KEYS[3],'owner')
if owner and owner~=ARGV[1] then return 0 end
redis.call('ZREM',KEYS[1],ARGV[1]); redis.call('ZREM',KEYS[2],ARGV[1])
redis.call('HSET',KEYS[3],'state','released','owner',ARGV[1])
redis.call('PEXPIRE',KEYS[3],86400000)
return 1
'''


class FleetAdmission:
    def __init__(self, redis, *, account='demo', user='tenant-a', global_limit=20,
                 user_limit=4, rpm=100, attempt_ms=2000, lease_ms=5000):
        if lease_ms <= attempt_ms or min(global_limit, user_limit, rpm, attempt_ms) < 1:
            raise ValueError('Invalid limits/lease')
        # Trusted server account/user; braces cannot inject a second cluster hash tag.
        account_id = hashlib.sha256(account.encode()).hexdigest()[:20]
        user_id = hashlib.sha256(user.encode()).hexdigest()
        self.prefix = 'admission:{' + account_id + '}'
        self.global_key, self.user_key = self.prefix + ':active', self.prefix + ':user:' + user_id
        self.rpm_key, self.flags_key = self.prefix + ':rpm', self.prefix + ':flags'
        self.user_id = user_id
        self.redis = redis
        self.admit_script, self.release_script = redis.register_script(ADMIT), redis.register_script(RELEASE)
        self.limits = [global_limit, user_limit, rpm]
        self.attempt_ms, self.lease_ms = attempt_ms, lease_ms

    def record_key(self, operation_id, attempt_no):
        digest = hashlib.sha256(f'{self.user_id}:{operation_id}:{attempt_no}'.encode()).hexdigest()
        return self.prefix + ':attempt:' + digest

    async def acquire(self, operation_id, attempt_no, owner):
        return await self.admit_script(keys=[self.global_key, self.user_key, self.rpm_key,
            self.record_key(operation_id, attempt_no), self.flags_key],
            args=[owner, self.lease_ms, self.attempt_ms, *self.limits])

    async def release(self, operation_id, attempt_no, owner):
        return await self.release_script(keys=[self.global_key, self.user_key,
            self.record_key(operation_id, attempt_no)], args=[owner])

    @asynccontextmanager
    async def attempt(self, operation_id, attempt_no):
        owner = uuid.uuid4().hex  # Stable across retries of this admission, not provider retries.
        try:
            result = None
            for recovery in range(2):
                try:
                    result = await self.acquire(operation_id, attempt_no, owner)
                    break
                except RedisError:
                    if recovery:
                        raise AdmissionTimeout('Admission state unavailable')
            if not result or not int(result[0]):
                raise AdmissionTimeout('Shared admission denied')
            yield
        finally:
            # Covers cancellation/ambiguous acquisition before yield as well.
            # An outage leaves a leased tombstone obligation, never an unbounded lease.
            try:
                async with asyncio.timeout(.5):
                    await finish(self.release(operation_id, attempt_no, owner))
            except (RedisError, TimeoutError):
                pass  # Emit an operational cleanup-failure metric in the host application.
