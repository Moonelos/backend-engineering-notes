"""Python 3.11+, nats-py 2.15.0; --demo owns a fresh disposable stream.
Normal mode binds an already-provisioned stream/consumer and retains an SQLite effect ledger.
"""
import argparse
import asyncio
import json
import signal
import sqlite3
import uuid

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy


async def process_one(message, handle, timeout=2.0):
    try:
        async with asyncio.timeout(timeout):
            await handle(json.loads(message.data))
    except asyncio.CancelledError:
        raise  # no acknowledgement; durable redelivery remains possible
    except Exception:
        await message.nak(delay=5)
    else:
        await message.ack_sync(timeout=1)  # durable effect precedes ack confirmation


async def run_worker(subscription, handle, stopping):
    while not stopping.is_set():
        try:
            messages = await subscription.fetch(batch=10, timeout=1)
        except nats.errors.TimeoutError:
            continue
        async with asyncio.TaskGroup() as tasks:
            for message in messages:
                tasks.create_task(process_one(message, handle))


async def main(args):
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopping.set)
    stream = 'DEMO_' + uuid.uuid4().hex if args.demo else 'ORDERS'
    subject = stream + '.created' if args.demo else 'orders.created'
    durable = 'bounded-worker'
    db = sqlite3.connect(':memory:' if args.demo else args.database)
    db.execute('CREATE TABLE IF NOT EXISTS effects(event_id TEXT PRIMARY KEY, order_id TEXT NOT NULL)')
    nc = await nats.connect(args.server)
    task = None
    try:
        js = nc.jetstream()
        if args.demo:
            await js.add_stream(name=stream, subjects=[subject])
        sub = await js.pull_subscribe(subject, durable=durable, stream=stream,
            config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL,
                                  ack_wait=10, max_ack_pending=10, max_deliver=5))
        observed = 0

        async def effect(event):
            nonlocal observed
            # This local SQL transaction is fast; production blocking DB I/O belongs off-loop
            # or in an async driver. A remote effect requires its own idempotency boundary.
            with db:
                db.execute('INSERT OR IGNORE INTO effects VALUES (?, ?)',
                           (event['event_id'], event['order_id']))
            observed += 1
            if args.demo and observed == 2:
                stopping.set()

        if args.demo:
            for _ in range(2):  # same business event in two independent stream deliveries
                await js.publish(subject, json.dumps({'event_id': 'evt-202', 'order_id': 'ord-84'}).encode())
        task = asyncio.create_task(run_worker(sub, effect, stopping))
        stop_waiter = asyncio.create_task(stopping.wait())
        try:
            # A task failure must not leave the supervisor waiting forever for a signal.
            done, _ = await asyncio.wait({task, stop_waiter}, timeout=15 if args.demo else None,
                                        return_when=asyncio.FIRST_COMPLETED)
            if not done: raise TimeoutError('demo did not finish')
            if task in done: await task
            stopping.set()
            await asyncio.wait_for(task, timeout=5)
        finally:
            stop_waiter.cancel()
            try: await stop_waiter
            except asyncio.CancelledError: pass
        if args.demo:
            count = db.execute('SELECT count(*) FROM effects').fetchone()[0]
            info = await js.consumer_info(stream, durable)
            assert count == 1 and info.num_ack_pending == 0
            print('PASS: 2 deliveries; 1 committed effect; 0 ack pending; bounded shutdown')
    finally:
        if task is not None and not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        if args.demo:
            await nc.jetstream().delete_stream(stream)
        try:
            await asyncio.wait_for(nc.drain(), timeout=5)
        except TimeoutError:
            await nc.close()
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', default='nats://127.0.0.1:4222')
    parser.add_argument('--database', default='worker-effects.sqlite')
    parser.add_argument('--demo', action='store_true')
    asyncio.run(main(parser.parse_args()))
