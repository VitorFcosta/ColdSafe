CREATE TABLE environment_rules (
    environment_id uuid PRIMARY KEY REFERENCES environments(id),
    temp_min_c numeric(5,2) NOT NULL DEFAULT 2,
    temp_max_c numeric(5,2) NOT NULL DEFAULT 8,
    recovery_margin_c numeric(5,2) NOT NULL DEFAULT 0.5,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (temp_min_c < temp_max_c),
    CHECK (recovery_margin_c >= 0),
    CHECK (recovery_margin_c * 2 < temp_max_c - temp_min_c)
);

-- An environment-wide rule cannot represent conflicting old device rules.
-- Stop transactionally rather than silently changing either device's limits.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM devices d
        JOIN rules r ON r.device_id = d.id
        GROUP BY d.environment_id
        HAVING count(DISTINCT (r.temp_min_c, r.temp_max_c, r.recovery_margin_c)) > 1
    ) THEN
        RAISE EXCEPTION 'conflicting device rules require resolution before migration 003';
    END IF;
END $$;

-- Preserve existing values, or defaults when an environment has no rule.
INSERT INTO environment_rules
    (environment_id, temp_min_c, temp_max_c, recovery_margin_c)
SELECT DISTINCT ON (e.id)
    e.id,
    COALESCE(r.temp_min_c, 2),
    COALESCE(r.temp_max_c, 8),
    COALESCE(r.recovery_margin_c, 0.5)
FROM environments e
LEFT JOIN devices d ON d.environment_id = e.id
LEFT JOIN rules r ON r.device_id = d.id
ORDER BY e.id, (r.device_id IS NULL), d.created_at, d.id;
