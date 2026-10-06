# Recovering data after a bad change

> **Reader:** You understand tables, transactions and the reviewed migration history in [Alembic](06_alembic.md). This operational lesson assumes ordinary shell use and PostgreSQL command-line tools. Teaching baseline: PostgreSQL 15–18, with a PostgreSQL 15 disposable rehearsal.

At 10:00, users 1 and 2 have tiers `free` and `pro`. At 10:04 an incorrect UPDATE makes both
`free` and commits. Rolling back the application stops further damage, but does not restore user
2's paid tier. A replica normally replays the same UPDATE. We need an independent earlier copy
and a tested way to turn it into a usable database.

A **backup** is a recoverable artifact kept independently of the running database. A **restore**
reconstructs a database from it. **Recovery** includes choosing the correct state, restoring it,
checking application invariants and routing traffic. A backup command returning zero proves that
an artifact was produced; a restore rehearsal proves substantially more.

## Decide how much loss and downtime the service can tolerate

**Recovery point objective (RPO)** is the maximum acceptable age of missing committed data.
**Recovery time objective (RTO)** is the maximum acceptable duration until service is usable again.
They are requirements, not properties automatically supplied by a backup schedule.

| Event | Latest recoverable state | Consequence |
|---|---|---|
| Logical dump starts 10:00; bad UPDATE 10:04 | Dump's consistent snapshot near 10:00 | Later valid writes need reconciliation |
| Base backup plus uninterrupted archived WAL; target before 10:04 | State immediately before bad transaction | Potentially much less lost work |
| Replica follows bad UPDATE | Same damaged state | Switching replica does not undo logical damage |

For an RPO of five minutes, a nightly dump alone cannot qualify. For an RTO of ten minutes,
restoring a 200 GB dump in an hour cannot qualify even if no data is lost. Measure detection,
artifact retrieval, provisioning, restore/replay, validation and traffic cutover together. Record
both achieved values in rehearsals and compare them to the service targets. Independent storage,
access controls and retention protect the backup from deletion or compromise of the live system;
retention must include the time needed to discover an unnoticed bad change.

## First prove a logical restore in a disposable database

`pg_dump` captures one database's consistent logical snapshot while ordinary writes continue.
A custom-format dump lets `pg_restore` reconstruct schema and data. It is useful for selected-table
recovery and portable logical inspection. It does not contain physical WAL history, other
databases or all cluster-level roles. Plan roles/extensions separately; `pg_dumpall --globals-only`
is one role-definition artifact, subject to privileged contents and controlled storage.
[Dump guarantees and limits](https://www.postgresql.org/docs/current/app-pgdump.html), checked 2026-10-06.

This complete rehearsal requires `psql`, `createdb`, `dropdb`, `pg_dump`, `pg_restore`, a dedicated
local test cluster and a test role allowed to create databases. `PGHOST`, `PGPORT` and `PGUSER`
must already select that cluster. Authenticate using a protected `.pgpass` or equivalent; do not
put passwords in shell history. The script creates two unique databases and removes only those
names. It never restores over an existing database.

```bash
#!/usr/bin/env bash
set -euo pipefail
scratch=$(mktemp -d)
suffix=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
source_db="recovery_source_${suffix}"
restore_db="recovery_restore_${suffix}"
cleanup() {
    [[ "$source_db" == recovery_source_* ]] && dropdb --if-exists "$source_db"
    [[ "$restore_db" == recovery_restore_* ]] && dropdb --if-exists "$restore_db"
    rm -rf "$scratch"
}
trap cleanup EXIT
createdb "$source_db"
createdb "$restore_db"
psql -X -v ON_ERROR_STOP=1 -d "$source_db" <<'SQL'
CREATE TABLE users (id integer PRIMARY KEY, name text NOT NULL, tier text NOT NULL);
INSERT INTO users VALUES (1, 'Alice', 'free'), (2, 'Bob', 'pro');
SQL
pg_dump --format=custom --file="$scratch/users.dump" "$source_db"
# Simulate a committed application bug only in the disposable source.
psql -X -v ON_ERROR_STOP=1 -d "$source_db" -c "UPDATE users SET tier = 'free';"
pg_restore --exit-on-error --no-owner --no-privileges \
    --dbname="$restore_db" "$scratch/users.dump"
actual=$(psql -X -At -v ON_ERROR_STOP=1 -d "$restore_db" \
    -c "SELECT id || ':' || name || ':' || tier FROM users ORDER BY id;")
[[ "$actual" == $'1:Alice:free\n2:Bob:pro' ]]
psql -X -v ON_ERROR_STOP=1 -d "$restore_db" <<'SQL'
DO $$ BEGIN
    IF (SELECT count(*) FROM users) <> 2 THEN
        RAISE EXCEPTION 'row count differs';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND contype = 'p'
    ) THEN
        RAISE EXCEPTION 'primary key missing';
    END IF;
END $$;
SQL
printf '%s\n' "$actual" 'restore verification passed'
```

Expected final output is `1:Alice:free`, `2:Bob:pro`, then `restore verification passed`.
The source now has Bob=`free`; the independently restored copy has Bob=`pro`. The row assertions
prove content, and the catalog assertion proves a schema property. A real application also checks
foreign-key integrity, key aggregates, extension availability, migration revision, permissions,
sequences and a read/write smoke test under its runtime role. `--no-owner --no-privileges` deliberately
uses the test role; it does not validate production grants.

Failure tells are concrete: `role does not exist` indicates missing ownership prerequisites unless
ownership is intentionally omitted; a missing extension requires compatible server packages;
`pg_restore` version errors can indicate tool/archive incompatibility. Use a dump client compatible
with the source server and restore tools compatible with that archive. Never ignore a nonzero
restore result because some tables happened to appear.

This toy rehearsal validates the recovery mechanism, not an application's complete recovery time.
For production, restore a realistically sized artifact into an isolated environment, measure the
whole procedure and keep a record of invariant checks. Encrypt artifacts as appropriate, restrict
who can read them, and test retrieval from independent storage rather than assuming a local dump
will survive host loss.

## When logical backups are insufficient: physical backup and WAL

A **physical base backup** copies the cluster's storage state using a supported backup protocol.
**Write-ahead log (WAL)** records changes needed to bring those files forward consistently.
A base backup plus an uninterrupted required WAL chain enables point-in-time recovery (PITR).
Copying a live data directory with ordinary filesystem commands is not a valid substitute: files
can represent different moments, and missing WAL prevents consistency.

```text
base backup B          archived WAL segments                recovery target
    |------------------------- replay --------------------------|
  09:00                09:30           10:03:59              STOP
                                             10:04 bad commit excluded
```

The replay starts from B, not from the dump. Each necessary WAL segment continues the history;
a missing segment before the target makes that target unreachable. WAL must be retained until
no retained base backup needs it. A replication slot retaining WAL on the live primary is not
independent archival storage and can fill the primary's disk if its consumer stops.
[Physical backup and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html).

A PITR deployment recipe, **not a complete runnable configuration**, is:

1. Configure durable, monitored WAL archiving before taking the base backup. The archive command
   must report success only after durable storage and must avoid overwriting a different segment
   under an existing name. Alert on archive failures, age of latest archived WAL and storage growth.
2. Take a supported physical base backup, such as `pg_basebackup`, retain its metadata and necessary
   WAL, and verify the backup manifest with `pg_verifybackup` where supported. Manifest verification
   checks the artifact; it does not prove that the desired recovery target is reachable.
3. Provision an isolated server using the compatible PostgreSQL major version and required
   extension binaries. Restore the base backup to its new data directory with correct ownership.
   Physical backups are tied to storage/version compatibility; logical export/import is the route
   when a major-version upgrade needs a different representation.
4. Configure `restore_command` to fetch archived WAL, create `recovery.signal`, and set an explicit
   target plus action. Start this isolated server, observe replay and confirm it actually reaches
   the intended target. A timestamp requires a correct timeline and an understood boundary;
   a named restore point or transaction target can make the intended event easier to identify.
5. Validate the recovered data before promotion and traffic routing. Retain the damaged system
   for forensics and possible extraction of later valid transactions; do not overwrite it with
   the first restore attempt.

Configuration excerpt for a recovery host after an actual base backup is installed:

```conf
restore_command = '/usr/local/bin/fetch-archived-wal %f %p'
recovery_target_time = '2026-10-06 10:03:59+03'
recovery_target_action = 'pause'
```

`fetch-archived-wal` is a deployment-owned executable, not supplied by these notes. `%f` identifies
the requested segment and `%p` its destination. Pausing lets the operator inspect the state before
promotion. It requires isolated recovery access; the database is not yet the writable replacement.
The teaching baseline does not promise a provider-specific archive implementation or failover
controller. Test those with your storage and platform, including archive retrieval failure and
missing-segment detection. [Recovery targets](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET),
[base backup](https://www.postgresql.org/docs/current/app-pgbasebackup.html),
[manifest verification](https://www.postgresql.org/docs/current/app-pgverifybackup.html).

## Choose the recovery boundary before routing writes

Restoring into isolation protects later valid data while you decide the scope of repair. If only
Bob's tier is wrong, compare the recovered rows and write a reviewed targeted repair in the current
database. If broad corruption requires a full replacement, establish a write freeze and reconcile
valid changes after the recovery target before routing traffic. Connections in application pools
may still point at the old server; drain/restart them during the cutover. A recovered schema's
Alembic revision must match the selected application release, otherwise startup can immediately
reapply the damaging migration or fail on missing columns.

Record the incident time, last known good event, chosen recovery target, selected artifact,
verification results, actual lost interval and actual time to restore service. Rehearsals should
include a failed restore and a missing backup, because the operating decision is often which
artifact still meets the RPO rather than whether the newest filename exists.

**Changed-condition checkpoint:** a dump at 10:00 is sound; a valid new user registers at 10:02;
the tier bug commits at 10:04. Does restoring the dump directly over production meet zero data
loss? No: it recovers Bob's tier but erases the 10:02 user. Restore separately, compare and repair
the damaged rows, or use validated PITR to a point after the registration and before the bug.
Neither route can reconstruct events absent from every artifact. A successful restore is useful
only when its resulting state satisfies the business requirement.
