-- A surviving Ollama loader can outlive its PostgreSQL lock session.
CREATE TABLE llm_memory_guard (
    id integer PRIMARY KEY CHECK (id = 1),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
