"""Explicit drop-new policy and measured drain; no disk/network sink."""
import logging
from logging.handlers import QueueHandler
import queue
import threading
import time

class DropNew(QueueHandler):
    def __init__(self, records):
        super().__init__(records);self.accepting=True;self.accepted=0;self.dropped=0
    def emit(self, record):
        # Handler.handle already holds the handler lock.
        if not self.accepting:
            self.dropped+=1;return
        try:self.queue.put_nowait(self.prepare(record));self.accepted+=1
        except queue.Full:self.dropped+=1
    def stop_admission(self):
        self.acquire()
        try:self.accepting=False
        finally:self.release()

def experiment(budget, sink_seconds):
    records=queue.Queue(maxsize=2);handler=DropNew(records)
    logger=logging.getLogger('notes.bounded');logger.setLevel(logging.INFO);logger.propagate=False;logger.addHandler(handler)
    entered=threading.Event();release=threading.Event();stop=threading.Event();written=[]
    def listen():
        while not stop.is_set() or not records.empty():
            try:record=records.get(timeout=.01)
            except queue.Empty:continue
            try:
                entered.set();release.wait(timeout=1)  # Test gate; not a production sink.
                time.sleep(sink_seconds)  # Models a sink with a known per-write bound.
                written.append(record.getMessage())
            finally:records.task_done()
    worker=threading.Thread(target=listen,daemon=True);worker.start()
    try:
        logger.info('event-0');assert entered.wait(1)
        for n in range(1,10):logger.info('event-%s',n)
        assert handler.accepted==3 and handler.dropped==7
        handler.stop_admission();stop.set();release.set()
        began=time.monotonic();worker.join(budget);elapsed=time.monotonic()-began
        complete=not worker.is_alive()
        print(f'accepted=3 dropped=7 written_at_deadline={len(written)} drain_complete={complete} elapsed={elapsed:.3f}s')
        # A service may now exit under its outer supervisor; this fixture waits solely to clean its known-bounded sink.
        worker.join(2);assert not worker.is_alive()
        assert len(written)==3
        return complete
    finally:
        release.set();stop.set();worker.join(2)
        logger.removeHandler(handler);handler.close()

if __name__=='__main__':
    assert experiment(1,.02)
    assert not experiment(.01,.1)
    print('PASS: saturation drops 7; complete drain and exceeded-deadline outcomes distinguished')
