import asyncio
import httpx

async def main():
    async def provider(request):
        return httpx.Response(200, json={'order': 'ord_42'})
    async with httpx.AsyncClient(base_url='https://provider.test',
            transport=httpx.MockTransport(provider),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=5),
            timeout=httpx.Timeout(connect=1, pool=.1, write=1, read=1)) as client:
        for _ in range(2):
            async with asyncio.timeout(2):
                response = await client.get('/orders/ord_42')
                response.raise_for_status()
                print(response.status_code, response.json())
    assert client.is_closed
    print('client closed')

if __name__ == '__main__':
    asyncio.run(main())
