BEGIN;
SET LOCAL statement_timeout = '10s';
CREATE ROLE tenant_lab_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE SCHEMA tenant_lab;
CREATE TABLE tenant_lab.documents (
    tenant_id bigint NOT NULL,
    id bigint NOT NULL,
    title text NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
INSERT INTO tenant_lab.documents VALUES (7, 42, 'Tenant seven'), (8, 42, 'Tenant eight');
ALTER TABLE tenant_lab.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_lab.documents FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_documents ON tenant_lab.documents TO tenant_lab_runtime
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint);
GRANT USAGE ON SCHEMA tenant_lab TO tenant_lab_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_lab.documents TO tenant_lab_runtime;
SET LOCAL ROLE tenant_lab_runtime;
SELECT set_config('app.tenant_id', '7', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM tenant_lab.documents) <> 1
       OR NOT EXISTS (SELECT 1 FROM tenant_lab.documents WHERE title = 'Tenant seven') THEN
        RAISE EXCEPTION 'tenant 7 isolation failed';
    END IF;
    RAISE NOTICE 'tenant 7 sees only its document';
    BEGIN
        INSERT INTO tenant_lab.documents VALUES (8, 43, 'Wrong tenant');
        RAISE EXCEPTION 'cross-tenant write unexpectedly accepted';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'tenant 7 cannot write tenant 8';
    END;
END $$;
SELECT set_config('app.tenant_id', '8', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM tenant_lab.documents) <> 1
       OR NOT EXISTS (SELECT 1 FROM tenant_lab.documents WHERE title = 'Tenant eight') THEN
        RAISE EXCEPTION 'tenant 8 isolation failed';
    END IF;
    RAISE NOTICE 'tenant 8 sees only its document';
END $$;
SELECT set_config('app.tenant_id', '', true);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM tenant_lab.documents) THEN
        RAISE EXCEPTION 'empty context exposed rows';
    END IF;
    RAISE NOTICE 'empty tenant context sees zero rows';
END $$;
RESET ROLE;
ROLLBACK;
