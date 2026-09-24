CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL CHECK (length(trim(email)) BETWEEN 3 AND 254),
    password_hash text NOT NULL CHECK (length(password_hash) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_unique ON users (lower(email));

CREATE TABLE sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    token_hash text NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE INDEX sessions_user_id_idx ON sessions (user_id);

CREATE TABLE environments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id),
    name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX environments_owner_user_id_idx ON environments (owner_user_id);

CREATE TABLE devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id uuid NOT NULL REFERENCES environments(id),
    mqtt_device_id text NOT NULL UNIQUE
        CHECK (mqtt_device_id ~ '^[A-Za-z0-9._-]{1,64}$'),
    name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX devices_environment_id_idx ON devices (environment_id);

CREATE TABLE rules (
    device_id uuid PRIMARY KEY REFERENCES devices(id),
    temp_min_c numeric(5,2) NOT NULL DEFAULT 2,
    temp_max_c numeric(5,2) NOT NULL DEFAULT 8,
    recovery_margin_c numeric(5,2) NOT NULL DEFAULT 0.5,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (temp_min_c < temp_max_c),
    CHECK (recovery_margin_c >= 0),
    CHECK (recovery_margin_c * 2 < temp_max_c - temp_min_c)
);

CREATE TABLE alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id uuid NOT NULL REFERENCES devices(id),
    kind text NOT NULL CHECK (kind IN ('temperature_low', 'temperature_high')),
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    CHECK (closed_at IS NULL OR closed_at >= opened_at)
);
CREATE INDEX alerts_device_opened_at_idx ON alerts (device_id, opened_at DESC);
CREATE UNIQUE INDEX alerts_one_open_kind_per_device
    ON alerts (device_id, kind) WHERE closed_at IS NULL;

CREATE TABLE actuator_commands (
    id uuid PRIMARY KEY,
    device_id uuid NOT NULL REFERENCES devices(id),
    requested_by_user_id uuid REFERENCES users(id),
    actuator text NOT NULL CHECK (actuator IN ('led', 'buzzer')),
    desired_on boolean NOT NULL,
    origin text NOT NULL CHECK (origin IN ('manual', 'automatic')),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'no_confirmation')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    deadline_at timestamptz NOT NULL,
    confirmed_at timestamptz,
    CHECK (deadline_at > requested_at),
    CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL)),
    CHECK ((origin = 'manual') = (requested_by_user_id IS NOT NULL))
);
CREATE INDEX actuator_commands_device_requested_at_idx
    ON actuator_commands (device_id, requested_at DESC);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id),
    device_id uuid REFERENCES devices(id),
    command_id uuid REFERENCES actuator_commands(id),
    event_type text NOT NULL CHECK (length(trim(event_type)) BETWEEN 1 AND 80),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_device_occurred_at_idx
    ON audit_events (device_id, occurred_at DESC);
