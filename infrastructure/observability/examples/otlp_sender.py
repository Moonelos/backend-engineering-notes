"""One loopback OTLP span; Collector log proves acceptance, not this print alone."""
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
    endpoint='http://127.0.0.1:14317', insecure=True, timeout=3)))
with provider.get_tracer('notes.otlp').start_as_current_span('checkout'):
    pass
flushed = provider.force_flush(timeout_millis=5000)
provider.shutdown()
if not flushed:
    raise RuntimeError('SDK flush deadline expired')
print('SDK queue flushed; require checkout in the Collector debug log')
