#!/bin/sh
# Download public weights only; runtime has neither internet access nor write access.
set -eu
ollama serve &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT
trap 'exit 1' INT TERM
attempt=0
until ollama list >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "Ollama did not start; weights were not prepared." >&2
        exit 1
    fi
    sleep 1
done
ollama pull llama3.2:3b-instruct-q4_K_M
