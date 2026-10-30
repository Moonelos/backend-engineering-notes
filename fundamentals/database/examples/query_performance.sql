BEGIN;
SET LOCAL statement_timeout = '30s';
CREATE TEMP TABLE perf_documents (
    id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    title text NOT NULL
) ON COMMIT DROP;
INSERT INTO perf_documents
SELECT n, n % 100, TIMESTAMPTZ '2026-01-01 00:00:00+00' + n * INTERVAL '1 second',
       'Document ' || n
FROM generate_series(1, 100000) AS n;
ANALYZE perf_documents;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, created_at FROM perf_documents
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 20;
CREATE INDEX ON perf_documents (tenant_id, created_at DESC, id DESC);
ANALYZE perf_documents;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, created_at FROM perf_documents
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 20;
SELECT id FROM perf_documents
WHERE tenant_id = 7 ORDER BY created_at DESC, id DESC LIMIT 20;
ROLLBACK;
