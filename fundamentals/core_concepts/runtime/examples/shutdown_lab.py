"""Standalone Unix service: durable local intent, cooperative drain and bounded closers."""
import argparse
import asyncio
import signal
import sqlite3
import time

async def serve(database: str, job_seconds: float, close_seconds: float, fail_job: bool = False):
    db=sqlite3.connect(database)
    db.executescript('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL); CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY);')
    with db:db.execute("INSERT OR IGNORE INTO jobs VALUES ('job-42','pending')")
    stop=asyncio.Event(); loop=asyncio.get_running_loop(); signal_count=0
    def request_stop():
        nonlocal signal_count
        signal_count+=1
        if not stop.is_set():
            stop.set();print('intake stopped',flush=True)
        else:print('repeated signal: cleanup remains single-owner',flush=True)
    for signum in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(signum,request_stop)
    async def work():
        print('job started',flush=True)
        await asyncio.sleep(job_seconds)
        if fail_job:
            raise RuntimeError('deliberate work failure')
        with db:
            db.execute("INSERT OR IGNORE INTO effects VALUES ('job-42')")
            db.execute("UPDATE jobs SET state='done' WHERE id='job-42'")
        print('effect committed',flush=True)
    async def close_client():
        await asyncio.sleep(close_seconds)
        print('client closed',flush=True)
    job=asyncio.create_task(work())
    stopping=asyncio.create_task(stop.wait())
    try:
        # Observe processing failures without waiting for an unrelated OS signal.
        done,_=await asyncio.wait({job,stopping},return_when=asyncio.FIRST_COMPLETED)
        if job in done:
            job.result()
            await stopping  # A completed job leaves this service ready for shutdown.
    finally:
        if not stop.is_set():
            stop.set();print('intake stopped after work failure or cancellation',flush=True)
        stopping.cancel()
        await asyncio.gather(stopping,return_exceptions=True)
        began=time.monotonic();deadline=loop.time()+.35
        try:
            # The drain owns only 200ms of the total cleanup budget.
            _,pending=await asyncio.wait({job},timeout=.2)
            if pending:
                job.cancel()
                print('drain expired; durable job remains retryable',flush=True)
            # This fixture cooperates immediately. Read failures without skipping closers.
            await asyncio.gather(job,return_exceptions=True)
            try:
                async with asyncio.timeout_at(deadline):await close_client()
            except TimeoutError:print('closer deadline expired',flush=True)
            print(f'drain and closer elapsed={time.monotonic()-began:.3f}s',flush=True)
        finally:
            db.close();print('database closed once',flush=True)
            for signum in (signal.SIGTERM,signal.SIGINT):loop.remove_signal_handler(signum)
    if not job.cancelled():
        job.result()  # Also surface failures that raced with the stop signal.

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('database');parser.add_argument('--job-seconds',type=float,default=.05);parser.add_argument('--close-seconds',type=float,default=.02);parser.add_argument('--fail-job',action='store_true')
    args=parser.parse_args();asyncio.run(serve(args.database,args.job_seconds,args.close_seconds,args.fail_job))
