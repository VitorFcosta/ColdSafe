# Configuração e segredos

Esta página separa configuração versionável de credenciais locais.

## Versões do projeto

- Python: `3.13.15`, registrado em `.python-version`.
- Node.js: `24.20.0`, registrado em `.nvmrc`.
- Dependências Python diretas: `backend/requirements-dev.txt`.
- Lock Python reproduzível: `backend/requirements-dev.lock.txt`.

A matriz completa, incluindo dependências ainda não instaladas e imagens Docker planejadas, está em [`docs/version-matrix.md`](version-matrix.md).

O computador pode ter outra versão instalada, mas desenvolvimento, Docker e CI devem convergir para as versões registradas. Não use tags `latest`, intervalos abertos ou atualizações automáticas silenciosas nos manifestos finais.

## Criar a configuração local

Na raiz do projeto:

```bash
cp .env.example .env
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

Depois, preencha somente os arquivos locais `.env` e `firmware/include/secrets.h`.

## Valores que precisam ser definidos localmente

No `.env`:

- `MQTT_BACKEND_PASSWORD`
- `MQTT_DEVICE_PASSWORD`
- `INFLUXDB_TOKEN`
- `DOCKER_INFLUXDB_INIT_USERNAME`
- `DOCKER_INFLUXDB_INIT_PASSWORD`
- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`

No `firmware/include/secrets.h`:

- manter o usuário `coldsafe-device`;
- substituir `REPLACE_WITH_MQTT_DEVICE_PASSWORD` pela mesma senha definida para o dispositivo no Mosquitto.

Os usuários MQTT são fixos por intenção: `coldsafe-device` só publica telemetria e
`coldsafe-backend` só lê telemetria e métricas `$SYS`. Compartilhar um único usuário
entre os dois quebraria essa separação de privilégios.

Não altere esses usuários nem `MQTT_TOPIC` apenas no `.env`: eles fazem parte do
contrato da ACL. Uma mudança futura precisa atualizar configuração, ACL, firmware e
testes em conjunto.

O SSID `Wokwi-GUEST`, o host `host.wokwi.internal` e o identificador `esp32-lab-01` são configurações demonstrativas, não credenciais.

## Permissões do token InfluxDB

`INFLUXDB_TOKEN` deve ser um token exclusivo do backend, com leitura e escrita
somente no bucket `telemetry`. Não reutilize `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`:
ele possui privilégios administrativos e deve ficar reservado à administração.

Com a CLI do container autenticada para administração, consulte o ID do bucket
usando `docker compose exec influxdb influx bucket list --name telemetry`.
Crie uma autorização com `influx auth create`, organização `coldsafe`, descrição
`coldsafe-backend-telemetry` e opções `--read-bucket` e `--write-bucket` apontando
para esse ID. Não use `--all-access` ou `--operator` para o backend.

Guarde o token retornado somente em `INFLUXDB_TOKEN` no `.env` local. Não copie o
valor para documentação, commits, Notion ou mensagens. Depois execute
`docker compose up -d --no-deps backend` para carregar a configuração alterada;
editar o `.env` não atualiza automaticamente o ambiente do container existente.

### Validação local da CS-36 — 10 de setembro de 2026

- O backend carregou o novo token, diferente do token administrador.
- A autorização contém somente leitura e escrita no bucket `telemetry`.
- Gravação e consulta reais passaram usando o token do backend, com um registro
  temporário em uma medição exclusiva de teste; o registro foi removido e sua
  ausência foi confirmada após a validação.
- A consulta à autorização administrativa com o token do backend retornou `401`.
- `/health/ready`, `/api/v1/monitoring/summary` e
  `/api/v1/readings?device_id=esp32-lab-01&period=24h&limit=1` retornaram `200`.

Esta evidência valida a correção do token; a revisão completa da CS-36 permanece
em andamento. A troca da credencial é uma operação local e não é versionada.

## Regras obrigatórias

1. Nunca colocar valores reais em `.env.example` ou `secrets.example.h`.
2. Nunca remover `.env` ou `secrets.h` do `.gitignore`.
3. Não registrar valores secretos em logs, mensagens de erro ou capturas de tela.
4. Credenciais de demonstração não podem ser reutilizadas em ambiente real.
5. Configuração ausente, vazia ou ainda contendo `REPLACE_WITH_...` deverá impedir readiness quando o backend for implementado.
6. Mensagens de erro podem indicar qual variável está ausente, mas nunca revelar seu valor.

## Instalar as dependências de teste

Para reproduzir exatamente o ambiente validado:

```bash
python3.13 --version
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock.txt
```

O primeiro comando precisa mostrar exatamente `Python 3.13.15`. Se `python3.13` não existir, instale o runtime antes de recriar a `.venv`; usar outra versão não é uma reprodução exata do ambiente planejado.

`requirements-dev.txt` lista apenas as dependências escolhidas diretamente; o arquivo de lock fixa também as dependências transitivas.
