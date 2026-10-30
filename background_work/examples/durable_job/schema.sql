CREATE TABLE IF NOT EXISTS document_inputs (
    ref TEXT PRIMARY KEY,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_parse_jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    request_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    input_ref TEXT NOT NULL REFERENCES document_inputs(ref),
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    retry_deadline TIMESTAMPTZ NOT NULL DEFAULT now() + interval '1 hour',
    attempt_token UUID,
    lease_expires_at TIMESTAMPTZ,
    result_ref TEXT,
    last_error_class TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE (tenant_id, request_key),
    CHECK ((status = 'RUNNING') = (attempt_token IS NOT NULL)),
    CHECK ((status = 'RUNNING') = (lease_expires_at IS NOT NULL)),
    CHECK ((status = 'SUCCEEDED') = (result_ref IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS document_parse_jobs_ready_idx
    ON document_parse_jobs (next_attempt_at, created_at) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS document_parse_jobs_expired_idx
    ON document_parse_jobs (lease_expires_at, id) WHERE status = 'RUNNING';
CREATE INDEX IF NOT EXISTS document_parse_jobs_budget_idx
    ON document_parse_jobs (retry_deadline, id) WHERE status = 'PENDING';
CREATE TABLE IF NOT EXISTS document_parse_results (
    job_id UUID PRIMARY KEY REFERENCES document_parse_jobs(id),
    words INTEGER NOT NULL CHECK (words >= 0)
);
CREATE TABLE IF NOT EXISTS job_outbox (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES document_parse_jobs(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
