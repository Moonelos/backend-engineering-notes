# PostgreSQL maintenance and diagnostics

Read [relational foundations](01_databases_and_schemas.md) first. This operational lesson assumes you can explain a transaction and run SQL. Its central question is why a database can grow or slow down even when the application still sees the same number of rows.

## An update leaves a version that another reader may need

Alice's account initially contains `balance = 100`. Session A opens a REPEATABLE READ transaction and reads that value. Session B updates it to 80 and commits. A still reads 100: its transaction uses the earlier snapshot. PostgreSQL must retain enough information to make that answer possible. An UPDATE creates a new row version; a DELETE marks a version as deleted. Neither immediately removes all physical evidence of the old row.

| Event | A's visible balance | A new transaction's balance | Cleanup consequence |
|---|---:|---:|---|
| A establishes its snapshot | 100 | 100 | Original version is live |
| B commits UPDATE to 80 | 100 | 80 | Old version remains needed by A |
| A commits | Transaction ended | 80 | Old version can become removable |
| VACUUM processes eligible versions | — | 80 | Space becomes reusable |

This is multiversion concurrency control (MVCC). Readers usually avoid blocking ordinary writers because they can use different versions. The price is cleanup work and retained storage. A long transaction can therefore hurt other workloads without holding a row lock that directly blocks their UPDATE.

### Replay the snapshot in two terminals

Use a disposable PostgreSQL database, with both terminals connected to the same database. Setup once:

```sql
CREATE TABLE mvcc_accounts (id integer PRIMARY KEY, balance integer NOT NULL);
INSERT INTO mvcc_accounts VALUES (1, 100);
```

Terminal A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM mvcc_accounts WHERE id = 1;
-- 100. Leave this transaction open while running B.
```

Terminal B:

```sql
UPDATE mvcc_accounts SET balance = 80 WHERE id = 1;
SELECT balance FROM mvcc_accounts WHERE id = 1;
-- 80, committed by psql autocommit.
VACUUM mvcc_accounts;
```

Return to A:

```sql
SELECT balance FROM mvcc_accounts WHERE id = 1;
-- Still 100: the vacuum cannot discard a version this snapshot needs.
COMMIT;
SELECT balance FROM mvcc_accounts WHERE id = 1;
-- 80: this statement starts with a new snapshot.
```

Then in B run `VACUUM mvcc_accounts; DROP TABLE mvcc_accounts;`. One update will not visibly change the filesystem size or reliably produce an exact statistics counter; the visible balance is the deterministic learning result. READ COMMITTED uses a new snapshot for each statement, so changing A's isolation level changes its second SELECT to 80 even before A commits. That is a visibility distinction, not a promise that every long READ COMMITTED transaction is harmless: inspect snapshot horizons, locks and open transactions separately.

## VACUUM, ANALYZE and disk shrinking solve different problems

Routine VACUUM makes eligible old-version space reusable, maintains the visibility map used by index-only scans, and freezes sufficiently old transaction IDs to prevent wraparound. ANALYZE samples current data distributions for planner estimates. `VACUUM (ANALYZE)` requests both operations, but an accurate histogram cannot remove an old row version needed by a snapshot.

Ordinary VACUUM generally leaves space inside the relation for later reuse. A stable table file after vacuum is therefore compatible with successful cleanup. `VACUUM FULL` rewrites a compact relation and requires an ACCESS EXCLUSIVE lock plus room for a new copy. Treat it as a planned maintenance operation with an outage/lock budget, rather than a routine response to a large file. Autovacuum runs ordinary vacuum and analyze as needed; it does not run VACUUM FULL. These behaviors are documented in [PostgreSQL 15 routine vacuuming](https://www.postgresql.org/docs/15/routine-vacuuming.html).

An append-only history table needs freezing even when it has few dead tuples. An update-heavy queue needs prompt cleanup and fresh statistics. These different workloads explain why one global setting rarely fits every table.

## Diagnose the retaining transaction before changing settings

The following are read-only diagnostic queries for a PostgreSQL 15+ connection. Full visibility of other sessions may require an appropriately granted monitoring role; do not give the application superuser access merely to collect diagnostics.

```sql
SELECT pid, usename, application_name, state,
       clock_timestamp() - xact_start AS transaction_age,
       backend_xmin, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;

SELECT relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_autoanalyze,
       autovacuum_count, autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;

SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

Suppose a queue has rising estimated dead tuples, an old `backend_xmin`, and an application session that has been idle in a transaction for 45 minutes. Investigate that session's owner and transaction boundary before increasing vacuum frequency. Vacuum cannot reclaim versions whose visibility horizon is still held back. Fix the application so it commits or rolls back before external HTTP calls or human interaction. [Connection pooling](05_connection_pooling.md) explains why the same leak can also exhaust connection capacity.

Conversely, if there is no old retaining horizon and the table changes rapidly between infrequent autovacuum runs, examine per-table trigger thresholds and worker/I/O capacity. On the PostgreSQL 15 baseline, ordinary update/delete vacuum eligibility uses a threshold plus a scale factor times estimated table rows, while insert-related and anti-wraparound triggers also exist. For a 10-million-row table, the common default update/delete calculation `50 + 0.2 × 10,000,000` waits for roughly two million changes. That calculation explains a possible delay; it is not a recommended target or a complete scheduling model. Consult the deployed server version's settings before tuning them.

Statistics are estimates and can lag; one `n_dead_tup` value is not a measurement of removable bytes. Collect a time series alongside relation size, write rate, autovacuum logs/progress, transaction age, CPU and storage latency. `pg_stat_progress_vacuum` reports active vacuum progress; `ANALYZE table_name` can refresh a badly outdated distribution after a bulk load. A bad estimate can also come from correlated columns or skew, so compare estimated and actual plan rows before concluding that statistics are stale. See [monitoring statistics](https://www.postgresql.org/docs/15/monitoring-stats.html) and [EXPLAIN](https://www.postgresql.org/docs/15/using-explain.html).

### Recover with the smallest justified intervention

First identify the owning request/job, its business effects, and whether it can be retried. Cancel a running query only through your authorized operational procedure. Cancellation does not close an idle transaction; its client must roll back. Termination disconnects the client and rolls back its open transaction, so it can trigger request failures and retries. Confirm that the horizon and blocker disappeared, then observe cleanup progress. Avoid automatically terminating every old connection: a deliberate backup or maintenance transaction may be doing useful work.

A transaction timeout policy bounds future leaks; it does not replace fixing their ownership. Driver and server timeout boundaries are explained in 05. For managed databases, the provider often owns vacuum worker settings and permissions; the backend team still owns long-lived application transactions, query shape, workload measurements and escalation evidence. Anti-wraparound warnings need prompt operator attention rather than disabling autovacuum.

## Replica freshness needs a position or a heartbeat

After Alice's primary transaction commits, a replica may still show the earlier balance until it replays the corresponding WAL. Replica reads have a different freshness contract from primary reads. To compare positions, collect a primary WAL position after commit and compare it to the replica's replay position in the same replication lineage. These are diagnostic excerpts for the indicated servers:

```sql
-- Primary, sampled after the write committed:
SELECT pg_current_wal_lsn();
-- Replica:
SELECT pg_last_wal_replay_lsn(), pg_is_in_recovery();
```

If the primary sample is `0/500` and the replica has replayed `0/480`, it has not yet reached that sample. Once replay reaches or passes `0/500`, the sample's preceding commit is included. A position comparison does not tell you elapsed seconds or prove every future read is current; failover changes lineage and a paused replay can still break a request deadline. A write that must immediately be read should use the primary, or an explicitly implemented bounded wait for the relevant position followed by a primary fallback.

`now() - pg_last_xact_replay_timestamp()` grows on an idle, fully caught-up replica because no newer transaction arrives. It is time since the last replayed commit, not unconditional current lag. For a time-based freshness objective, a periodic committed heartbeat gives an intentional stream of timestamps; measure its replica age and account for clock skew and heartbeat outages. A replica also replays accidental deletes, which is why [backup and recovery](08_backup_and_recovery.md) requires independent history.

## Transfer: choose the next measurement

A support report says “disk grew 20%, vacuum ran, and the replica lag chart says 30 minutes.” No writes occurred during the last 30 minutes. Should you run VACUUM FULL and fail over?

The supplied evidence supports neither action. Ordinary vacuum may have created reusable space without shrinking the file; compare write volume, relation size trends, retaining snapshots and estimated dead tuples. The replica timestamp may simply reflect inactivity; compare WAL positions or a heartbeat before declaring it stale. Failover does not remove bloat and may select a less current server. If the real issue is an old application snapshot, ending that transaction enables cleanup while failover only adds disruption.
