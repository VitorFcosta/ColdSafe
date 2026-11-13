-- History and its canonical prediction commit together before the telemetry ACK.
CREATE TABLE inference_events (
    source_event_id uuid PRIMARY KEY,
    owner_user_id uuid NOT NULL REFERENCES users(id),
    device_record_id uuid NOT NULL REFERENCES devices(id),
    environment_id uuid NOT NULL REFERENCES environments(id),
    equipment_id uuid NOT NULL,
    received_at timestamptz NOT NULL,
    source jsonb NOT NULL CHECK (jsonb_typeof(source) = 'object'),
    prediction_event_id uuid NOT NULL UNIQUE,
    prediction jsonb NOT NULL CHECK (jsonb_typeof(prediction) = 'object'),
    published_at timestamptz
);
CREATE INDEX inference_events_history_idx ON inference_events
    (owner_user_id, device_record_id, equipment_id, received_at, source_event_id);
CREATE INDEX inference_events_pending_idx ON inference_events
    (owner_user_id, device_record_id, received_at, source_event_id)
    WHERE published_at IS NULL;
