# ColdSafe

Protótipo acadêmico para monitorar temperatura e umidade em um ambiente refrigerado.

> O ColdSafe não é um sistema médico, sanitário ou regulatório certificado.

## Estrutura do projeto

- `contracts/`: contratos compartilhados entre firmware, backend e frontend.
- `backend/`: ingestão MQTT, regras de domínio, persistência e API.
- `frontend/`: dashboard operacional em Vue.
- `firmware/`: ESP32, DHT22 e simulação no Wokwi.
- `infra/`: Mosquitto, InfluxDB e configuração Docker.

## Fase atual

A infraestrutura local, o firmware ESP32/Wokwi, o domínio, o assinante MQTT, o
repositório InfluxDB e a API FastAPI estão implementados. O fluxo MQTT →
classificação → InfluxDB → API está validado em containers reais.

A composição desktop e mobile do frontend foi aprovada. O dashboard consome a
API, apresenta diagnóstico atual, gráfico por período, polling, falhas parciais
e todos os estados operacionais previstos. Responsividade, acessibilidade e os
fluxos E2E também foram validados. O ensaio completo com Wokwi, reinício e
persistência está registrado em
[`docs/testing/demo-rehearsal.md`](docs/testing/demo-rehearsal.md). O marco
pendente do MVP é concluir a revisão de segurança.

## Testes de contrato

```bash
python3.13 --version
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock.txt
.venv/bin/python -m pytest backend/tests
```

Testes marcados como `integration` são ignorados quando as variáveis da
infraestrutura descartável não estão definidas. O procedimento completo está em
[`docs/testing/influxdb-repository.tdd.md`](docs/testing/influxdb-repository.tdd.md).

## Configuração local

As versões do projeto estão fixadas em `.python-version` e `.nvmrc`; a matriz completa está em [`docs/version-matrix.md`](docs/version-matrix.md). Para criar os arquivos locais de configuração:

```bash
cp .env.example .env
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

Preencha os arquivos copiados sem alterar os exemplos versionados. Leia as regras completas em [`docs/configuration.md`](docs/configuration.md).

## Quick start

O primeiro uso exige criar um token do InfluxDB exclusivo do backend; por isso,
não use o token administrativo como atalho. Siga o procedimento completo e
seguro em [`docs/runbook.md`](docs/runbook.md).

Depois que o `.env`, o `firmware/include/secrets.h` e o token restrito estiverem
configurados, o fluxo diário é:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Abra [http://localhost:5173](http://localhost:5173). Para encerrar sem apagar o
histórico persistido, execute `docker compose down`.

## Convenção de commits

O ColdSafe usa Conventional Commits no formato `tipo(escopo): descrição`.

Exemplo:

```text
feat(contracts): define contrato inicial de telemetria
```

Leia a regra completa em [`docs/commit-conventions.md`](docs/commit-conventions.md) e ative o template local com:

```bash
git config --local commit.template .gitmessage
```
