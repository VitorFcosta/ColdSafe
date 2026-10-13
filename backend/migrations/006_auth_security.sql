-- Preserve legacy sessions while identifying all new JWT sessions explicitly.
ALTER TABLE sessions ADD COLUMN token_kind text NOT NULL DEFAULT 'opaque'
    CHECK (token_kind IN ('opaque', 'jwt'));

CREATE TABLE login_rate_limits (
    key_hash text PRIMARY KEY CHECK (length(key_hash) = 64),
    attempts integer NOT NULL CHECK (attempts > 0),
    window_started_at timestamptz NOT NULL
);

CREATE TABLE websocket_tickets (
    token_hash text PRIMARY KEY CHECK (length(token_hash) = 64),
    session_id uuid NOT NULL REFERENCES sessions(id),
    device_id uuid NOT NULL REFERENCES devices(id),
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK (expires_at > issued_at),
    CHECK (expires_at <= issued_at + interval '60 seconds'),
    CHECK (consumed_at IS NULL OR consumed_at >= issued_at)
);
CREATE INDEX websocket_tickets_session_id_idx ON websocket_tickets (session_id);
