-- Job events have account scope and cannot share the device-only AIoT outbox.
CREATE TABLE job_outbox (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    job_id uuid NOT NULL REFERENCES jobs(id),
    publisher_role text NOT NULL CHECK (publisher_role IN ('api', 'generation', 'training')),
    event jsonb NOT NULL CHECK (jsonb_typeof(event) = 'object'),
    published_at timestamptz
);
CREATE INDEX job_outbox_pending_idx ON job_outbox(publisher_role, sequence)
    WHERE published_at IS NULL;
CREATE UNIQUE INDEX job_outbox_one_request_idx ON job_outbox(job_id)
    WHERE publisher_role = 'api';
