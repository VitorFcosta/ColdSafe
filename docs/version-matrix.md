# Matriz de versões do ColdSafe

Esta é a referência versionada para o bootstrap do projeto. Uma dependência planejada só deve ser instalada quando sua fatia começar; depois da instalação, o arquivo de lock correspondente passa a registrar a resolução exata.

Não usar `latest`, `^` ou `~` nos manifestos finais.

## Runtimes

| Tecnologia | Versão |
| --- | --- |
| Node.js | `24.20.0` |
| Python | `3.13.15` |

## Frontend planejado

| Pacote | Versão-base |
| --- | --- |
| create-vue | `3.23.0` |
| Vue / compiler-sfc | `3.5.42` |
| Vue Router | `5.3.0` |
| Vite / plugin-vue | `8.2.2` / `6.0.8` |
| TypeScript | `7.0.2` |
| Tailwind CSS / plugin Vite | `4.3.3` / `4.3.3` |
| Chart.js / vue-chartjs | `4.5.1` / `5.3.4` |
| Vitest | `4.1.11` |
| Vue Testing Library | `8.1.0` |
| Playwright | `1.62.1` |
| openapi-typescript | `7.13.0` |

## Backend e testes planejados

| Pacote | Versão-base |
| --- | --- |
| FastAPI | `0.141.1` |
| Uvicorn | `0.52.4` |
| Pydantic / Pydantic Settings | `2.13.5` / `2.15.0` |
| paho-mqtt | `2.1.0` |
| influxdb-client | `1.50.0` |
| pytest / pytest-cov | `9.1.1` / `7.1.0` |
| HTTPX / jsonschema | `0.28.1` / `4.26.0` |

As dependências de teste já instaladas e suas transitivas estão fixadas em `backend/requirements-dev.lock.txt`.

## Firmware planejado

| Pacote | Versão-base |
| --- | --- |
| PlatformIO espressif32 | `7.0.1` |
| DHT sensor library | `1.4.7` |
| PubSubClient | `2.8` |
| ArduinoJson | `7.4.3` |

## Imagens Docker planejadas

| Imagem | Tag fixada |
| --- | --- |
| node | `24.20.0-alpine3.24` |
| python | `3.13.15-slim` |
| influxdb | `2.7.12-alpine` |
| eclipse-mosquitto | `2.0.22` |

## Regra de atualização

1. Alterar uma dependência por necessidade real, não apenas porque existe versão mais nova.
2. Atualizar primeiro esta matriz e o manifesto da área.
3. Regenerar o lock sem editar dependências transitivas manualmente.
4. Executar build, testes e auditoria de segurança aplicáveis.
5. Registrar no commit o motivo da atualização.
