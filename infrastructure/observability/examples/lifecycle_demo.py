"""In-process FastAPI lifecycle proof with a real OTel SDK batch exporter."""
import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


async def main():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=60000))
    tracer = provider.get_tracer('notes.lifecycle')

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            assert provider.force_flush(timeout_millis=3000)
            provider.shutdown()

    app = FastAPI(lifespan=lifespan)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    @app.get('/checkout')
    async def checkout():
        with tracer.start_as_current_span('checkout'):
            return {'accepted': True}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
            response = await client.get('/checkout')
            assert response.status_code == 200
        assert not exporter.get_finished_spans()  # response is complete; batch is still buffered
    assert any(span.name == 'checkout' for span in exporter.get_finished_spans())
    print('PASS: HTTP 200 before export; checkout exported by lifespan shutdown')


if __name__ == '__main__':
    asyncio.run(main())
