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

A composição desktop e mobile do frontend foi aprovada, e a fundação Vue,
Tailwind, Docker e tokens visuais já está criada. O diagnóstico atual consome a
API e apresenta carregamento, ausência de dados, estados operacionais e erro de
serviço. A próxima fatia é implementar o gráfico e os períodos; polling e
falhas parciais do histórico vêm depois.

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
