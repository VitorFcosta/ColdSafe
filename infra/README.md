# Infraestrutura local

O Compose padrão inclui a pilha AIoT v3, com Mosquitto, RabbitMQ, InfluxDB,
PostgreSQL, aplicação Web, simulador, gateway, writer, workers e Ollama.
A base explícita (`-f compose.yaml`) serve para comissionamento e para o
percurso legado. Veja os [serviços e fluxos](../docs/aiot/architecture.md).

`mosquitto-init` prepara credenciais MQTT antes de iniciar o Mosquitto.
`rabbitmq-init` prepara as definições do RabbitMQ, com filas duráveis,
credenciais por serviço, tentativas limitadas e fila de mensagens mortas (DLQ).
Consulte a [topologia e os testes do RabbitMQ](rabbitmq/README.md).

Prepare contas, catálogo e tokens pelo [runbook](../docs/runbook.md).

## Preparar variáveis locais

O [bootstrap](../docs/runbook.md#3-inicializar-o-influxdb-e-provisionar-tokens-restritos)
cria as permissões de leitura/escrita do backend legado e a permissão de escrita
do writer v3. O backend aplica as migrações PostgreSQL ao iniciar. Consulte o
[guia de configuração](../docs/configuration.md) para as variáveis de cada serviço.

## Credenciais MQTT

O `mosquitto-init` gera automaticamente o arquivo de senhas no volume nomeado
`mosquitto-auth`, usando `MQTT_BACKEND_PASSWORD`, `MQTT_DEVICE_PASSWORD` e
`MQTT_DEVICE_02_PASSWORD` do `.env`. Quando preenchidas, inclui também as duas
credenciais `MQTT_SIMULATOR_*_PASSWORD` opcionais. Não crie um arquivo `passwords` manualmente.
A ACL limita cada dispositivo aos próprios tópicos de telemetria, comandos e
confirmações.

## Subir e verificar

Com o comissionamento e o preparo de pesos concluídos:

```bash
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 420
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

O [modo Wokwi](../docs/runbook.md#esp32wokwi-legado) e o
[diagnóstico da pilha completa](../docs/runbook.md#6-diagnóstico) publicam
API `8000`, MQTT `1883` e gerenciamento RabbitMQ `15672` em loopback.

## Parar sem apagar o histórico

```bash
docker compose down
```

Não use `docker compose down --volumes` no fluxo normal: essa opção apaga os
volumes nomeados e, com eles, o histórico do InfluxDB. As credenciais de
inicialização do InfluxDB só são aplicadas quando o volume está vazio.
O mesmo cuidado preserva usuários, ambientes e configurações no PostgreSQL.
