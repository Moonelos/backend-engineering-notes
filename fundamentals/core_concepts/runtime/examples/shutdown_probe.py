"""Send real signals only to subprocesses created here; temporary SQLite state."""
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
script=Path(__file__).with_name('shutdown_lab.py')
def start(db,seconds,close=.02,fail=False):
    command=[sys.executable,'-u',str(script),str(db),'--job-seconds',str(seconds),'--close-seconds',str(close)]
    if fail:command.append('--fail-job')
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
    if not selector.select(4):child.kill();raise AssertionError('no started marker')
    line=child.stdout.readline();selector.close();assert 'job started' in line,line
    return child,line

def state(db):
    with sqlite3.connect(db) as conn:return conn.execute('SELECT state FROM jobs').fetchone()[0],conn.execute('SELECT count(*) FROM effects').fetchone()[0]
with tempfile.TemporaryDirectory(prefix='notes-shutdown-') as directory:
    for label,seconds,close,expected in [('drain',.05,.02,('done',1)),('overrun',5,5,('pending',0))]:
        db=Path(directory)/(label+'.db');child,initial=start(db,seconds,close);began=time.monotonic()
        child.send_signal(signal.SIGTERM);time.sleep(.015);child.send_signal(signal.SIGTERM)
        output=initial+child.communicate(timeout=3)[0]
        assert child.returncode==0,output
        assert output.count('database closed once')==1 and 'repeated signal' in output,output
        assert state(db)==expected,(output,state(db))
        assert time.monotonic()-began<2
        print(label+': '+output.replace('\n','; '))
    db=Path(directory)/'kill.db';child,initial=start(db,5);child.kill();child.communicate(timeout=3)
    assert child.returncode==-signal.SIGKILL and state(db)==('pending',0)
    child,initial=start(db,.03);child.send_signal(signal.SIGTERM);output=child.communicate(timeout=3)[0]
    assert child.returncode==0 and state(db)==('done',1),output
    print('PASS: repeated SIGTERM, bounded drain/closer, SIGKILL leaves pending, restart commits one effect')
    db=Path(directory)/'failure.db';child,initial=start(db,.02,fail=True)
    output=initial+child.communicate(timeout=3)[0]  # No shutdown signal: error triggers cleanup.
    assert child.returncode!=0,output
    assert 'deliberate work failure' in output and 'client closed' in output,output
    assert output.count('database closed once')==1,output
    assert state(db)==('pending',0)
    print('PASS: work error exits without a signal, closes client/database, and preserves pending intent')
