-- v3 state is isolated from the legacy MQTT command scheduler.
CREATE TABLE aiot_inbox (
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    device_id uuid NOT NULL REFERENCES devices(id),
    envelope jsonb NOT NULL,
    PRIMARY KEY (consumer, event_id)
);
CREATE TABLE aiot_events (
    event_id uuid PRIMARY KEY,
    device_id uuid NOT NULL REFERENCES devices(id),
    kind text NOT NULL,
    received_at timestamptz NOT NULL,
    source_event_id uuid,
    linked boolean NOT NULL DEFAULT false,
    envelope jsonb NOT NULL
);
CREATE INDEX aiot_events_device_received_idx ON aiot_events (device_id, kind, received_at DESC);
CREATE INDEX aiot_events_source_idx ON aiot_events (source_event_id);
CREATE TABLE aiot_commands (
    command_id uuid PRIMARY KEY,
    device_id uuid NOT NULL REFERENCES devices(id),
    actuator text NOT NULL CHECK (actuator IN ('led', 'buzzer')),
    desired_state boolean NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'confirmed', 'rejected', 'unconfirmed')),
    accepted_at timestamptz NOT NULL,
    deadline_at timestamptz NOT NULL CHECK (deadline_at > accepted_at),
    envelope jsonb NOT NULL,
    status_envelope jsonb NOT NULL
);
CREATE INDEX aiot_commands_device_idx ON aiot_commands (device_id, actuator, accepted_at DESC);
CREATE TABLE aiot_alerts (
    alert_id uuid PRIMARY KEY,
    device_id uuid NOT NULL REFERENCES devices(id),
    kind text NOT NULL CHECK (kind IN ('temperature_low', 'temperature_high')),
    opened_at timestamptz NOT NULL,
    closed_at timestamptz CHECK (closed_at >= opened_at),
    envelope jsonb NOT NULL
);
CREATE UNIQUE INDEX aiot_alerts_open_idx ON aiot_alerts (device_id, kind) WHERE closed_at IS NULL;
CREATE TABLE aiot_freshness (
    device_id uuid PRIMARY KEY REFERENCES devices(id),
    state text NOT NULL CHECK (state IN ('no_data', 'fresh', 'stale'))
);
CREATE TABLE aiot_outbox (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    device_id uuid NOT NULL REFERENCES devices(id),
    envelope jsonb NOT NULL,
    published_at timestamptz
);
CREATE INDEX aiot_outbox_pending_idx ON aiot_outbox (sequence) WHERE published_at IS NULL;
