BEGIN;
SET LOCAL statement_timeout = '10s';
CREATE TEMP TABLE model_tenants (id bigint PRIMARY KEY, name text NOT NULL);
CREATE TEMP TABLE model_documents (
    tenant_id bigint NOT NULL REFERENCES model_tenants(id),
    id bigint NOT NULL,
    name text NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, id),
    CHECK (state IN ('pending', 'processing', 'ready', 'failed'))
);
CREATE UNIQUE INDEX model_live_document_name
ON model_documents (tenant_id, name) WHERE deleted_at IS NULL;
INSERT INTO model_tenants VALUES (7, 'Acme');
INSERT INTO model_documents (tenant_id, id, name) VALUES (7, 42, 'invoice.pdf');
DO $$
BEGIN
    BEGIN
        INSERT INTO model_documents (tenant_id, id, name) VALUES (7, 43, 'invoice.pdf');
        RAISE EXCEPTION 'duplicate unexpectedly accepted';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'duplicate live name rejected';
    END;
END $$;
UPDATE model_documents SET deleted_at = now() WHERE tenant_id = 7 AND id = 42;
INSERT INTO model_documents (tenant_id, id, name) VALUES (7, 43, 'invoice.pdf');
DO $$
BEGIN
    BEGIN
        UPDATE model_documents SET state = 'invented' WHERE tenant_id = 7 AND id = 43;
        RAISE EXCEPTION 'invalid state unexpectedly accepted';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'invalid state rejected';
    END;
END $$;
SELECT id, name FROM model_documents WHERE tenant_id = 7 AND deleted_at IS NULL;
ROLLBACK;
