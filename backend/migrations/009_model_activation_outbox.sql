-- Requests and status transitions must survive an AMQP outage with their effects.
CREATE TABLE model_outbox (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    activation_id uuid NOT NULL REFERENCES model_activations(id),
    publisher_role text NOT NULL CHECK (publisher_role IN ('api', 'inference')),
    event jsonb NOT NULL CHECK (jsonb_typeof(event) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX model_outbox_pending_idx ON model_outbox(publisher_role, sequence)
    WHERE published_at IS NULL;
CREATE UNIQUE INDEX model_outbox_one_request_idx ON model_outbox(activation_id)
    WHERE publisher_role = 'api';
