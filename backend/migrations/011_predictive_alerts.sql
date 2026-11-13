CREATE TABLE predictive_rules (
    owner_user_id uuid PRIMARY KEY REFERENCES users(id),
    health_critical double precision NOT NULL DEFAULT 30 CHECK (health_critical >= 0),
    health_recovery double precision NOT NULL DEFAULT 40 CHECK (health_recovery <= 100),
    rul_critical_hours double precision NOT NULL DEFAULT 24 CHECK (rul_critical_hours >= 0),
    rul_recovery_hours double precision NOT NULL DEFAULT 48 CHECK (rul_recovery_hours < 'Infinity'::float8),
    open_count integer NOT NULL DEFAULT 3 CHECK (open_count BETWEEN 1 AND 100),
    close_count integer NOT NULL DEFAULT 10 CHECK (close_count BETWEEN 1 AND 100),
    CHECK (health_critical < health_recovery),
    CHECK (rul_critical_hours < rul_recovery_hours)
);

CREATE TABLE predictive_state (
    owner_user_id uuid NOT NULL REFERENCES users(id),
    device_id uuid NOT NULL REFERENCES devices(id),
    equipment_id uuid NOT NULL,
    last_source_event_id uuid REFERENCES aiot_events(event_id),
    last_input_at timestamptz,
    last_model_id uuid REFERENCES models(id),
    critical_streak integer NOT NULL DEFAULT 0 CHECK (critical_streak >= 0),
    recovery_streak integer NOT NULL DEFAULT 0 CHECK (recovery_streak >= 0),
    health_score double precision,
    rul_hours double precision,
    trend text NOT NULL DEFAULT 'unknown' CHECK (trend IN ('unknown','stable','improving','declining')),
    PRIMARY KEY (owner_user_id,device_id,equipment_id)
);

CREATE TABLE predictive_alerts (
    alert_id uuid PRIMARY KEY,
    owner_user_id uuid NOT NULL REFERENCES users(id),
    device_id uuid NOT NULL REFERENCES devices(id),
    equipment_id uuid NOT NULL,
    opened_at timestamptz NOT NULL,
    closed_at timestamptz CHECK (closed_at >= opened_at),
    source_event_id uuid NOT NULL REFERENCES aiot_events(event_id),
    prediction_event_id uuid NOT NULL REFERENCES aiot_events(event_id),
    closed_prediction_event_id uuid REFERENCES aiot_events(event_id)
);
CREATE UNIQUE INDEX predictive_alerts_one_open ON predictive_alerts
    (owner_user_id,device_id,equipment_id) WHERE closed_at IS NULL;
