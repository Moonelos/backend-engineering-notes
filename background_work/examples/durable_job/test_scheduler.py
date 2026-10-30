from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import threading
from uuid import uuid4
from zoneinfo import ZoneInfo

import store


def resolve_local(local, zone_name, gap="shift", fold="both"):
    """Minute-granularity calendar rule; round-trip to reject imaginary times."""
    zone = ZoneInfo(zone_name)
    def candidates(wall):
        values = {wall.replace(tzinfo=zone, fold=f).astimezone(timezone.utc) for f in (0, 1)}
        return sorted(v for v in values if v.astimezone(zone).replace(tzinfo=None) == wall)
    valid = candidates(local)
    if not valid and gap == "skip":
        return []
    for _ in range(24 * 60):
        if valid:
            break
        local += timedelta(minutes=1)
        valid = candidates(local)
    if not valid:
        raise ValueError("no valid minute within one day")
    return valid if fold == "both" else valid[:1] if fold == "first" else valid[-1:]


def init_schedule(schedule_id, due):
    with store.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules(
              id UUID PRIMARY KEY, next_fire_at TIMESTAMPTZ NOT NULL,
              enabled BOOLEAN NOT NULL DEFAULT true);
            CREATE TABLE IF NOT EXISTS schedule_firings(
              id UUID PRIMARY KEY, schedule_id UUID REFERENCES schedules(id),
              scheduled_for TIMESTAMPTZ NOT NULL, UNIQUE(schedule_id,scheduled_for));
            """)
        conn.execute("INSERT INTO schedules(id,next_fire_at) VALUES (%s,%s)",(schedule_id,due))


def fire(schedule_id, due):
    # The cursor is deliberately not advanced here: tests simulate the crash
    # between durable firing and cursor advancement by calling this twice.
    content = "scheduled report"
    digest = hashlib.sha256(content.encode()).hexdigest()
    key = str(schedule_id) + ":" + due.astimezone(timezone.utc).isoformat()
    with store.connect() as conn:
        conn.execute("INSERT INTO document_inputs VALUES (%s,%s) ON CONFLICT DO NOTHING",(digest,content))
        return conn.execute("""
            WITH firing AS (
              INSERT INTO schedule_firings(id,schedule_id,scheduled_for)
              SELECT %s,id,%s FROM schedules WHERE id=%s AND enabled
              ON CONFLICT(schedule_id,scheduled_for) DO NOTHING RETURNING id
            ), job AS (
              INSERT INTO document_parse_jobs(id,tenant_id,request_key,request_hash,input_ref,status)
              SELECT %s,%s,%s,%s,%s,'PENDING' FROM firing RETURNING id
            ), delivery AS (
              INSERT INTO job_outbox(id,job_id) SELECT %s,id FROM job
            ) SELECT id FROM job
            """, (uuid4(),due,schedule_id,uuid4(),store.TENANT,key,digest,digest,uuid4())).fetchone()


def test_dst_and_gap():
    spring = resolve_local(datetime(2026,3,29,3,30),'Europe/Athens')
    assert [v.isoformat() for v in spring] == ['2026-03-29T01:00:00+00:00']
    fall = resolve_local(datetime(2026,10,25,3,30),'Europe/Athens')
    assert [v.isoformat() for v in fall] == ['2026-10-25T00:30:00+00:00','2026-10-25T01:30:00+00:00']
    assert resolve_local(datetime(2026,3,29,3,30),'Europe/Athens',gap='skip') == []


def test_replica_race_and_stale_cursor():
    schedule_id = uuid4()
    due = datetime(2026,3,29,1,tzinfo=timezone.utc)
    init_schedule(schedule_id,due)
    barrier = threading.Barrier(2)
    def replica(_):
        barrier.wait(timeout=5)
        return fire(schedule_id,due)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(replica,range(2)))
    assert sum(row is not None for row in results) == 1
    assert fire(schedule_id,due) is None  # restart with unchanged next_fire_at
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM schedule_firings WHERE schedule_id=%s",(schedule_id,)).fetchone()['n'] == 1
        conn.execute("UPDATE schedules SET enabled=false WHERE id=%s",(schedule_id,))
    assert fire(schedule_id,due+timedelta(days=1)) is None


def test_bounded_catchup():
    anchor = datetime(2026,1,1,tzinfo=timezone.utc)
    missed = [anchor + timedelta(days=n) for n in range(5)]
    assert missed[-1:] == [anchor+timedelta(days=4)]  # coalesce
    assert missed[:2] == [anchor,anchor+timedelta(days=1)]  # oldest two
