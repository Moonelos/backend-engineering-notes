"""Application heartbeat state; the connection's single reader calls observe()."""
import asyncio
import secrets


class Heartbeat:
    def __init__(self):
        self.pending = None
        self.acknowledged = asyncio.Event()

    def observe(self, message):
        if self.pending is not None and message.get('type') == 'pong' and message.get('nonce') == self.pending:
            self.acknowledged.set()

    async def probe(self, outbound, stop, timeout=10):
        self.pending = secrets.token_hex(8)
        self.acknowledged.clear()
        try:
            # Queue admission, send delay and reply share this deadline.
            async with asyncio.timeout(timeout):
                await outbound.put({'type': 'ping', 'nonce': self.pending})
                await self.acknowledged.wait()
            return True
        except TimeoutError:
            stop.set()  # Supervisor cancels and joins reader/writer, then closes.
            return False
        finally:
            self.pending = None
