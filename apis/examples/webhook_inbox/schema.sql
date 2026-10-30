CREATE TABLE webhook_inbox (
    producer text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'received',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error_code text,
    processed_at timestamptz,
    PRIMARY KEY (producer, event_id)
);
CREATE TABLE invoices (
 id text PRIMARY KEY,
 status text NOT NULL DEFAULT 'open',
 effect_count integer NOT NULL DEFAULT 0
);
CREATE TABLE processed_provider_events (
 producer text NOT NULL, event_id text NOT NULL,
 processed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (producer, event_id)
);
INSERT INTO invoices (id) VALUES ('inv_123');
