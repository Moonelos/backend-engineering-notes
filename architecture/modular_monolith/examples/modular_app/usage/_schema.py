SCHEMA = """
CREATE TABLE accepted_answers (
    tenant TEXT NOT NULL,
    request_id TEXT NOT NULL,
    units INTEGER NOT NULL CHECK (units = 1),
    PRIMARY KEY (tenant, request_id)
);
"""
