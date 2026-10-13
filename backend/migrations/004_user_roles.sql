-- Keep existing account capabilities; public registration cannot supply a role.
ALTER TABLE users ADD COLUMN role text NOT NULL DEFAULT 'operator'
    CHECK (role IN ('viewer', 'operator', 'admin'));
