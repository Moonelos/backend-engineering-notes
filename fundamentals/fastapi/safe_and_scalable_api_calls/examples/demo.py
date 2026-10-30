import asyncio
import httpx
from bounded_calls import BoundedCaller, AdmissionTimeout

async def main():
    attempts = 0
    async def provider(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={'order': 'ord_42', 'status': 'paid'})

    async with httpx.AsyncClient(base_url='https://provider.test',
            transport=httpx.MockTransport(provider),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(1.0)) as client:
        caller = BoundedCaller(client, capacity=1, max_waiters=0, jitter=lambda n: 0)
        print(await caller.request_json('GET', '/orders/ord_42'))
        print('attempts', caller.attempts_started, 'active', caller.gate.active)
        await caller.gate.acquire()
        try:
            await caller.request_json('GET', '/orders/ord_42')
        except AdmissionTimeout:
            print('local_overload; provider_attempts', caller.attempts_started)
        finally:
            await caller.gate.release()

if __name__ == '__main__':
    asyncio.run(main())
