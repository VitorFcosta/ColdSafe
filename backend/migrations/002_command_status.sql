ALTER TABLE actuator_commands
    DROP CONSTRAINT IF EXISTS actuator_commands_status_check;

UPDATE actuator_commands
SET status = 'unconfirmed'
WHERE status = 'no_confirmation';

ALTER TABLE actuator_commands
    ADD CONSTRAINT actuator_commands_status_check
    CHECK (status IN ('pending', 'confirmed', 'rejected', 'unconfirmed'));
