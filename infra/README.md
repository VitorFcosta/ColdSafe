# Infraestrutura local

O Docker Compose executa Mosquitto, InfluxDB, PostgreSQL, backend FastAPI e frontend Vue. O
serviço efêmero `mosquitto-init` prepara as credenciais do broker antes do
Mosquitto iniciar.

A B2-07 acrescenta RabbitMQ interno e inicializador offline, filas duráveis,
credenciais por serviço, retry limitado e DLQ privada. Preparação, topologia e
testes estão em [`rabbitmq/README.md`](rabbitmq/README.md). O backend v1/v2
continua no MQTT; o gravador v3 foi acrescentado na B2-12 e os demais consumidores são posteriores.

A B2-09 acrescenta o perfil opcional `simulator`, produtor MQTT v3 com seis
sensores e desgaste progressivo. Usa duas credenciais exclusivas, cadastro local
montado em leitura e controles operacionais separados dos comandos de atuadores.
Veja [`simulator/README.md`](../simulator/README.md). A aplicação v1/v2 ainda não
consome essas leituras; a entrega não comprova integração MQTT→RabbitMQ→Web.

A B2-11 acrescenta o perfil `aiot`, gateway MQTT/AMQP bidirecional com diário
SQLite no volume privado `gateway-state`, validação PostgreSQL de propriedade e
deduplicação entre reinícios. Veja [`gateway/README.md`](../gateway/README.md).
A B2-12 acrescenta `writer` ao mesmo perfil, com fila própria, token InfluxDB
write-only e bucket `telemetry_live` separado do legado/sintéticos. Preparação e
testes em [`writer/README.md`](../writer/README.md).
O dashboard v3 continua posterior; a API v1/v2 conserva seu transporte.

O procedimento canônico para preparar outro computador, criar o token restrito
do InfluxDB, subir os serviços, validar o sistema e diagnosticar falhas está em
[`../docs/runbook.md`](../docs/runbook.md).

## Preparar variáveis locais

Na raiz do projeto:

```bash
python3 scripts/generate-secrets.py
```

O gerador preenche segredos ausentes/vazios sem trocar valores existentes e
mantém o `.env` privado com `0600`. Configure
`MQTT_DEVICE_PASSWORD` e `MQTT_DEVICE_02_PASSWORD` com senhas diferentes e use
cada uma no ESP32 correspondente. O
backend deve receber um `INFLUXDB_TOKEN` exclusivo, com leitura e escrita
somente no bucket de telemetria; nunca reutilize o token administrativo.
Defina também `POSTGRES_PASSWORD` no `.env` local. O backend aplica a migração
relacional versionada ao iniciar; ela não modifica o histórico do InfluxDB.

## Credenciais MQTT

O `mosquitto-init` gera automaticamente o arquivo de senhas no volume nomeado
`mosquitto-auth`, usando `MQTT_BACKEND_PASSWORD`, `MQTT_DEVICE_PASSWORD` e
`MQTT_DEVICE_02_PASSWORD` do `.env`. Quando preenchidas, inclui também as duas
credenciais `MQTT_SIMULATOR_*_PASSWORD` opcionais. Não crie um arquivo `passwords` manualmente.
A ACL limita cada dispositivo aos próprios tópicos de telemetria, comandos e
confirmações.

## Subir e verificar

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

Somente `127.0.0.1:5173` é publicado no modo normal. O frontend estático encaminha
REST, documentação e WebSocket ao backend interno. API, MQTT, RabbitMQ e bancos
participam somente da rede interna; apenas o frontend também participa da borda.
Backend e frontend executam sem root e com filesystem de leitura, usando `/tmp`
efêmero. Os volumes nomeados dos bancos e brokers permanecem preservados.

As imagens locais dos brokers incluem configuração, ACL e inicializador estáticos;
senhas e definições geradas continuam em volumes privados. Após editar
`infra/mosquitto` ou `infra/rabbitmq`, use `docker compose up -d --build --wait`.
Não há montagem de arquivos dessa pasta nos brokers durante a execução.

Para Wokwi/diagnóstico, use `docker compose -f compose.yaml -f compose.debug.yaml
up -d --build --wait`: API `8000`, MQTT `1883` e management RabbitMQ `15672`
ficam disponíveis somente em loopback. Veja o [runbook](../docs/runbook.md)
para bootstrap do token InfluxDB, links de diagnóstico e retorno ao modo normal.

## Parar sem apagar o histórico

```bash
docker compose down
```

Não use `docker compose down --volumes` no fluxo normal: essa opção apaga os
volumes nomeados e, com eles, o histórico do InfluxDB. As credenciais de
inicialização do InfluxDB só são aplicadas quando o volume está vazio.
O mesmo cuidado preserva usuários, ambientes e configurações no PostgreSQL.
