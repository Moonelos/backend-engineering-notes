import asyncio
import os
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import pytest
from advanced_db import connect, initialize
from advanced_idempotency import claim, complete_local, Conflict, Busy, StaleOwner, provider_key
from advanced_budget import reserve, start_attempt, record_usage, settle, BudgetDenied


def setup_module():
    initialize()


def test_concurrent_duplicate_changed_body_and_tenant_scope():
    tenant, key = uuid.uuid4().hex, uuid.uuid4().hex
    barrier = threading.Barrier(2)
    def call():
        barrier.wait()
        try:
            return complete_local(claim(tenant,'POST /payments',key,{'amount':100}),100)
        except Busy:
            return 'busy'
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _:call(),range(2)))
    replay = claim(tenant,'POST /payments',key,{'amount':100})
    assert replay.replay == complete_local(replay,100)
    assert outcomes.count('busy') <= 1
    with pytest.raises(Conflict):
        claim(tenant,'POST /payments',key,{'amount':200})
    other = complete_local(claim('other-'+tenant,'POST /payments',key,{'amount':200}),200)
    assert other[1]['payment_id'] != replay.id
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM advanced_payments WHERE operation_id=%s',(replay.id,)).fetchone()['n']==1
    assert provider_key(tenant,'POST /payments',key) != provider_key('other-'+tenant,'POST /payments',key)


def test_expired_generation_rejects_old_owner():
    tenant = uuid.uuid4().hex
    old = claim(tenant,'POST /payments','key',{'amount':100})
    with connect() as db:
        db.execute("UPDATE advanced_idempotency SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(old.id,))
    new = claim(tenant,'POST /payments','key',{'amount':100})
    assert new.generation == old.generation+1
    with pytest.raises(StaleOwner):
        complete_local(old,100)
    assert complete_local(new,100)[0]==201


def test_process_loss_after_effect_rolls_back_before_reclaim():
    tenant = uuid.uuid4().hex
    owner = claim(tenant,'POST /payments','crash',{'amount':100})
    code = f'from advanced_idempotency import Claim, complete_local; complete_local(Claim({owner.id},{owner.generation}),100,crash_after_effect=True)'
    result = subprocess.run([sys.executable,'-c',code],cwd=os.path.dirname(__file__))
    assert result.returncode==17
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM advanced_payments WHERE operation_id=%s',(owner.id,)).fetchone()['n']==0
        db.execute("UPDATE advanced_idempotency SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(owner.id,))
    assert complete_local(claim(tenant,'POST /payments','crash',{'amount':100}),100)[0]==201


def test_all_attempt_usage_midnight_and_duplicate_settlement():
    op, tenant = uuid.uuid4().hex, uuid.uuid4().hex
    original = date(2026,10,30)
    reserve(op,tenant,input_cap=500,output_cap=1000,max_attempts=2,ceiling=5000,window=original)
    assert start_attempt(op,0,500)=={'max_output_tokens':1000}
    record_usage(op,0,1200)  # Provider reports billed work even though attempt failed.
    start_attempt(op,1,500)
    record_usage(op,1,800)
    assert reserve(op,tenant,input_cap=500,output_cap=1000,max_attempts=2,ceiling=5000,
                   window=date(2026,10,31))['window_date']==original
    assert settle(op)==settle(op)==2000
    record_usage(op,1,800)  # Duplicate evidence is harmless.
    with connect() as db:
        row=db.execute('SELECT * FROM advanced_budget_windows WHERE tenant=%s',(tenant,)).fetchone()
        assert (row['spent'],row['reserved'],row['window_date'])==(2000,0,original)


def test_unknown_cancel_and_process_loss_hold_reservation():
    tenant = uuid.uuid4().hex
    for mode in ['missing','cancelled','process-loss']:
        op = uuid.uuid4().hex
        reserve(op,tenant,input_cap=500,output_cap=1000,max_attempts=1,ceiling=10000)
        if mode=='process-loss':
            code=f'from advanced_budget import start_attempt; import os; start_attempt({op!r},0,100); os._exit(17)'
            assert subprocess.run([sys.executable,'-c',code],cwd=os.path.dirname(__file__)).returncode==17
        else:
            start_attempt(op,0,100)
            if mode=='cancelled':
                async def cancelled():
                    task=asyncio.create_task(asyncio.sleep(10))
                    await asyncio.sleep(0)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError): await task
                asyncio.run(cancelled())
            record_usage(op,0,None)
        assert settle(op) is None
        with connect() as db:
            row=db.execute('SELECT * FROM advanced_budget_ops WHERE operation_id=%s',(op,)).fetchone()
            assert row['state']=='UNKNOWN' and row['reservation']==1500
        record_usage(op,0,800)  # Later provider evidence allows guarded reconciliation.
        assert settle(op)==800


def test_final_budget_capacity_race():
    tenant, barrier = uuid.uuid4().hex, threading.Barrier(2)
    def submit(_):
        barrier.wait()
        try:
            reserve(uuid.uuid4().hex,tenant,input_cap=500,output_cap=500,max_attempts=1,ceiling=1000)
            return 'reserved'
        except BudgetDenied:
            return 'denied'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit,range(2)))==['denied','reserved']
