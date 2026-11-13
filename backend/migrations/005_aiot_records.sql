-- Ownership participates in every relation, including optional environment scope.
ALTER TABLE environments ADD CONSTRAINT environments_id_owner_unique
    UNIQUE (id, owner_user_id);

CREATE TABLE datasets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id),
    generation_job_id uuid,
    generation_job_type text GENERATED ALWAYS AS ('generation'::text) STORED,
    name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    features_version text NOT NULL CHECK (length(trim(features_version)) BETWEEN 1 AND 80),
    row_count bigint NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    artifact_key text CHECK (
        artifact_key ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$'
        AND artifact_key !~ '(^|/)\.\.?(/|$)' AND artifact_key !~ '//'
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_user_id),
    UNIQUE (id, owner_user_id, generation_job_id)
);
CREATE INDEX datasets_owner_created_idx ON datasets (owner_user_id, created_at DESC);

CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id),
    environment_id uuid,
    job_type text NOT NULL CHECK (job_type IN ('generation', 'training')),
    dataset_id uuid,
    config jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config) = 'object'),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    completed_units bigint NOT NULL DEFAULT 0,
    total_units bigint NOT NULL CHECK (total_units > 0),
    result_dataset_id uuid,
    result_model_id uuid,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now() CHECK (updated_at >= created_at),
    UNIQUE (id, owner_user_id),
    UNIQUE (id, owner_user_id, job_type),
    UNIQUE (id, owner_user_id, dataset_id),
    FOREIGN KEY (environment_id, owner_user_id) REFERENCES environments (id, owner_user_id),
    FOREIGN KEY (dataset_id, owner_user_id) REFERENCES datasets (id, owner_user_id),
    FOREIGN KEY (result_dataset_id, owner_user_id, id)
        REFERENCES datasets (id, owner_user_id, generation_job_id),
    CHECK ((job_type = 'generation' AND dataset_id IS NULL)
        OR (job_type = 'training' AND dataset_id IS NOT NULL AND total_units = 2)),
    CHECK (completed_units BETWEEN 0 AND total_units),
    CHECK (status <> 'queued' OR completed_units = 0),
    CHECK (
        (status = 'completed' AND completed_units = total_units AND (
            (job_type = 'generation' AND result_dataset_id IS NOT NULL AND result_model_id IS NULL)
            OR (job_type = 'training' AND result_model_id IS NOT NULL AND result_dataset_id IS NULL)))
        OR (status <> 'completed' AND result_dataset_id IS NULL AND result_model_id IS NULL)
    ),
    CHECK (
        (status = 'failed' AND error_code IS NOT NULL AND (
            (job_type = 'generation' AND error_code = 'GENERATION_FAILED')
            OR (job_type = 'training' AND error_code = 'TRAINING_FAILED')))
        OR (status <> 'failed' AND error_code IS NULL)
    )
);
CREATE INDEX jobs_owner_created_idx ON jobs (owner_user_id, created_at DESC);
ALTER TABLE datasets ADD CONSTRAINT datasets_generation_job_owner_type_fk
    FOREIGN KEY (generation_job_id, owner_user_id, generation_job_type)
        REFERENCES jobs (id, owner_user_id, job_type);

-- One model is the package containing both health and RUL regressions.
CREATE TABLE models (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id),
    dataset_id uuid NOT NULL,
    training_job_id uuid NOT NULL,
    model_version text NOT NULL CHECK (length(trim(model_version)) BETWEEN 1 AND 80),
    features_version text NOT NULL CHECK (length(trim(features_version)) BETWEEN 1 AND 80),
    artifact_key text NOT NULL CHECK (
        artifact_key ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$'
        AND artifact_key !~ '(^|/)\.\.?(/|$)' AND artifact_key !~ '//'
    ),
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metrics) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, owner_user_id),
    UNIQUE (id, owner_user_id, training_job_id),
    UNIQUE (owner_user_id, model_version),
    FOREIGN KEY (dataset_id, owner_user_id) REFERENCES datasets (id, owner_user_id),
    FOREIGN KEY (training_job_id, owner_user_id, dataset_id)
        REFERENCES jobs (id, owner_user_id, dataset_id)
);
CREATE INDEX models_owner_created_idx ON models (owner_user_id, created_at DESC);
ALTER TABLE jobs ADD CONSTRAINT jobs_result_model_owner_fk
    FOREIGN KEY (result_model_id, owner_user_id, id)
        REFERENCES models (id, owner_user_id, training_job_id);

CREATE TABLE model_activations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id),
    model_id uuid NOT NULL,
    previous_model_id uuid,
    status text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'loading', 'active', 'failed')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now() CHECK (updated_at >= created_at),
    FOREIGN KEY (model_id, owner_user_id) REFERENCES models (id, owner_user_id),
    FOREIGN KEY (previous_model_id, owner_user_id) REFERENCES models (id, owner_user_id),
    CHECK ((status = 'failed' AND error_code IS NOT NULL AND error_code = 'MODEL_LOAD_FAILED')
        OR (status <> 'failed' AND error_code IS NULL))
);
CREATE INDEX model_activations_owner_created_idx ON model_activations (owner_user_id, created_at DESC);
CREATE UNIQUE INDEX model_activations_one_pending_per_owner
    ON model_activations (owner_user_id) WHERE status IN ('ready', 'loading');

-- This pointer records a package per owner; loading/swapping it belongs to B2-24/25.
CREATE TABLE active_models (
    owner_user_id uuid PRIMARY KEY REFERENCES users(id),
    model_id uuid NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (model_id, owner_user_id) REFERENCES models (id, owner_user_id)
);
