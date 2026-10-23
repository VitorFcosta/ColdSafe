# Matriz de versões do ColdSafe

Versões efetivas da entrega local. Os manifestos e locks do repositório são a
fonte exata; esta tabela facilita a conferência no computador da apresentação.

| Camada | Versões principais | Fonte |
| --- | --- | --- |
| Runtime backend | Python `3.13.15` | `.python-version`, `backend/Dockerfile` |
| Runtime frontend | Node `24.20.0` | `.nvmrc`, `frontend/Dockerfile` |
| Backend | FastAPI `0.141.1`, Pydantic `2.13.5`, psycopg `3.3.6`, pwdlib `0.3.1`, paho-mqtt `2.1.0`, influxdb-client `1.50.0`, websockets `17.1` | `backend/requirements.txt`, `backend/requirements.lock.txt` |
| Transporte HTTP do InfluxDB | urllib3 `2.8.0`; correção das três vulnerabilidades identificadas em `2.7.0` em 14/10/2026 | `backend/requirements.txt`, locks de produção/desenvolvimento; [evidência](evidence/urllib3-security-fix.json) |
| Autenticação B2-06 | PyJWT `2.15.1`, bcrypt `5.0.0`; pwdlib com extras Argon2/bcrypt | `backend/requirements.txt`, locks de produção/desenvolvimento |
| Testes Python | pytest `9.1.1`, pytest-cov `7.1.0`, HTTPX `0.28.1`, jsonschema `4.26.0` | `backend/requirements-dev.txt`, `backend/requirements-dev.lock.txt` |
| Transporte AMQP B2-07/11 | RabbitMQ `4.3.6-management-alpine`; Pika `1.4.4` nos testes e no gateway | `compose.yaml`, `infra/rabbitmq/`, manifesto/lock dev, `gateway/requirements.txt` |
| Gateway B2-11 | Python `3.13.15-slim`, Pika `1.4.4`, psycopg/binary `3.3.6`, paho-mqtt `2.1.0`, jsonschema `4.26.0`; SQLite da biblioteca padrão | `gateway/Dockerfile`, `gateway/requirements.txt`, `simulator/requirements.txt` |
| Gravador B2-12 | Python `3.13.15-slim`; versões do gateway + influxdb-client `1.50.0`, urllib3 `2.8.0`, Pydantic `2.13.5` e transitivas já fixadas no lock backend | `writer/Dockerfile`, `writer/requirements.txt` |
| API AMQP B2-13 | Pika `1.4.4` e jsonschema `4.26.0` promovidos do lock dev ao runtime backend, sem atualizar versões existentes | Manifesto/locks backend, `backend/app/amqp/`, `compose.aiot.yaml` |
| Gerador offline B2-18 | NumPy `2.5.4`; Python `3.13.15`; armazenamento `offline-numpy-v1` | Manifesto/locks backend, `backend/app/services/generation.py` |
| Regressão de saúde B2-21 | scikit-learn `1.9.1`; SciPy `1.18.1`, joblib `1.6.0`, threadpoolctl `3.7.0`, narwhals `2.27.1`, cloudpickle `3.1.2`; NumPy preservado | Manifesto/locks backend, `backend/app/services/health_training.py` |
| Simulador B2-09 | Python `3.13.15-slim`, paho-mqtt `2.1.0`, jsonschema `4.26.0`; quatro transitivas nas versões existentes do lock dev | `simulator/Dockerfile`, `simulator/requirements.txt` |
| Frontend estático B2-08 | Nginx unprivileged `1.31.6`, base `1.31-alpine3.24` fixada pelo digest `sha256:884e0b7f42f303641b0f4e78755aea647521dca0b89ca3be7992ad78b5c07434` | `frontend/Dockerfile`, `frontend/nginx.conf` |
| Frontend | Vue `3.5.42`, Vue Router `5.3.0`, Vite `8.2.2`, TypeScript `6.0.3`, Chart.js `4.5.1`, Playwright `1.63.0`, Vitest `4.1.11` | `frontend/package.json`, `frontend/package-lock.json` |
| Cena 3D B2-27 | Three.js `0.186.1`; desenvolvimento: `@types/three 0.186.0` | `frontend/package.json`, `frontend/package-lock.json` |
| LLM local B2-30/B2-32 | Ollama `0.40.3`; `llama3.2:3b-instruct-q4_K_M`, CPU/contexto 1.024, quatro threads, lote 128, 3,25 GiB/4 CPUs | `compose.ollama.yaml`, `backend/app/services/llm.py`; pesos no volume local; aceite factual no cartão B2-32 |
| Firmware | espressif32 `7.0.1`, DHT sensor library for ESPx `1.19`, MQTT `2.5.3`, ArduinoJson `7.4.3` | `firmware/platformio.ini` |
| Containers | Mosquitto `2.0.22`, InfluxDB `2.7.12-alpine`, PostgreSQL `17.11-alpine3.24`, Python `3.13.15-slim`, Node `24.20.0-alpine3.24` | `compose.yaml`, Dockerfiles |

TypeScript `6.0.3` permanece fixado porque `vue-tsc 3.3.11` não é compatível
com o TypeScript 7 usado no planejamento inicial. Nenhuma dependência nova foi
necessária para o bloco de validação e documentação.

Para atualizar uma versão, altere o manifesto e o lock da camada, rode seus
testes e build, e registre o motivo no commit. Não use tags `latest` nem faixas
abertas nos manifestos finais.
