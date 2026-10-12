# Matriz de versões do ColdSafe

Versões efetivas da entrega local. Os manifestos e locks do repositório são a
fonte exata; esta tabela facilita a conferência no computador da apresentação.

| Camada | Versões principais | Fonte |
| --- | --- | --- |
| Runtime backend | Python `3.13.15` | `.python-version`, `backend/Dockerfile` |
| Runtime frontend | Node `24.20.0` | `.nvmrc`, `frontend/Dockerfile` |
| Backend | FastAPI `0.141.1`, Pydantic `2.13.5`, psycopg `3.3.6`, pwdlib `0.3.1`, paho-mqtt `2.1.0`, influxdb-client `1.50.0`, websockets `17.1` | `backend/requirements.txt`, `backend/requirements.lock.txt` |
| Testes Python | pytest `9.1.1`, pytest-cov `7.1.0`, HTTPX `0.28.1`, jsonschema `4.26.0` | `backend/requirements-dev.txt`, `backend/requirements-dev.lock.txt` |
| Frontend | Vue `3.5.42`, Vue Router `5.3.0`, Vite `8.2.2`, TypeScript `6.0.3`, Chart.js `4.5.1`, Playwright `1.63.0`, Vitest `4.1.11` | `frontend/package.json`, `frontend/package-lock.json` |
| Firmware | espressif32 `7.0.1`, DHT sensor library for ESPx `1.19`, MQTT `2.5.3`, ArduinoJson `7.4.3` | `firmware/platformio.ini` |
| Containers | Mosquitto `2.0.22`, InfluxDB `2.7.12-alpine`, PostgreSQL `17.11-alpine3.24`, Python `3.13.15-slim`, Node `24.20.0-alpine3.24` | `compose.yaml`, Dockerfiles |

TypeScript `6.0.3` permanece fixado porque `vue-tsc 3.3.11` não é compatível
com o TypeScript 7 usado no planejamento inicial. Nenhuma dependência nova foi
necessária para o bloco de validação e documentação.

Para atualizar uma versão, altere o manifesto e o lock da camada, rode seus
testes e build, e registre o motivo no commit. Não use tags `latest` nem faixas
abertas nos manifestos finais.
