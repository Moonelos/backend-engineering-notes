SCHEMA = """
CREATE TABLE conversations (
    tenant TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    PRIMARY KEY (tenant, conversation_id)
);
CREATE TABLE answers (
    tenant TEXT NOT NULL,
    request_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    PRIMARY KEY (tenant, request_id),
    FOREIGN KEY (tenant, conversation_id)
        REFERENCES conversations (tenant, conversation_id)
);
"""
