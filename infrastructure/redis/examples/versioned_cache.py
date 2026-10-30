"""Redis 7+ guarded fills: reject old values after a version-floor event was applied.
This closes stale repopulation, not the asynchronous DB-commit -> invalidation lag.
"""
ADVANCE = '''
local version = tonumber(ARGV[1])
local floor = tonumber(redis.call('GET', KEYS[1]) or '-1')
if version > floor then redis.call('SET', KEYS[1], version); floor = version end
local cached = tonumber(redis.call('HGET', KEYS[2], 'version') or '-1')
if cached < floor then redis.call('DEL', KEYS[2]) end
return floor
'''
FILL = '''
local raw_floor = redis.call('GET', KEYS[1])
if not raw_floor then return -1 end
local version = tonumber(ARGV[1])
local floor = tonumber(raw_floor)
local cached = tonumber(redis.call('HGET', KEYS[2], 'version') or '-1')
if version < floor or version < cached then return 0 end
redis.call('HSET', KEYS[2], 'version', version, 'payload', ARGV[2])
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
'''


async def demonstrate(r, prefix):
    floor, value = prefix + ':floor', prefix + ':value'
    await r.eval(ADVANCE, 2, floor, value, 7)  # authoritative DB version at bootstrap
    # Reader retains a v7 result while another transaction commits v8.
    await r.eval(ADVANCE, 2, floor, value, 8)  # consume durable v8 invalidation
    assert await r.eval(FILL, 2, floor, value, 7, 'Alice', 60) == 0
    assert await r.eval(FILL, 2, floor, value, 8, 'Bob', 60) == 1
    assert await r.eval(ADVANCE, 2, floor, value, 7) == 8  # reordered invalidation
    assert await r.hget(value, 'payload') == 'Bob'
    await r.delete(floor)  # simulate loss of fencing state
    assert await r.eval(FILL, 2, floor, value, 7, 'Alice', 60) == -1
    # Bypass cache, reload authoritative floor, then resume permitted fills.
    await r.eval(ADVANCE, 2, floor, value, 8)
    assert await r.eval(FILL, 2, floor, value, 8, 'Bob', 60) == 1
    print('PASS: v7 rejected after v8; old invalidation ignored; missing floor fails closed')
