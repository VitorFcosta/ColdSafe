# Gravador de telemetria — B2-12

Worker Python opcional do perfil `aiot`: consome somente `coldsafe.writer`,
valida telemetria v3 e grava no InfluxDB antes de confirmar ao RabbitMQ.
Não consome a fila da API nem entrega WebSocket. A API/dashboard v1/v2 continuam
consultando o histórico legado; a consulta HTTP v3 pertence às próximas tarefas.

## Preparar

1. Prepare o cadastro privado e os brokers conforme o [gateway](../gateway/README.md).
   `WRITER_OWNER_USER_ID` deve ser o UUID do mesmo proprietário esperado no PostgreSQL.
   O writer monta o mesmo `SIMULATOR_CATALOG_DIR/catalog.json` em leitura.
2. Com a CLI Influx autenticada como administrador, crie o bucket
   `telemetry_live` na organização `coldsafe`, com retenção inicial de 7 dias:

   ```sh
   docker compose exec influxdb influx bucket create --name telemetry_live --org coldsafe --retention 168h
   docker compose exec influxdb influx bucket list --name telemetry_live
   ```

   Não recrie o bucket se ele já existir. Não altere o bucket legado `telemetry`.
   Anote o ID de `telemetry_live` e crie uma autorização exclusiva com
   `influx auth create --org coldsafe --description coldsafe-writer-live --write-bucket ID_DO_BUCKET`.
   Não acrescente leitura, `--all-access` ou `--operator`.
3. Guarde o token retornado apenas em `INFLUXDB_WRITER_TOKEN` no `.env` privado,
   diferente de `INFLUXDB_TOKEN` e do token administrador. O gerador de segredos
   deixa esse campo vazio: uma string aleatória não cria autorização no banco.
   O serviço não recebe o token legado nem o administrador.
4. Confira/inicie explicitamente os serviços:

   ```sh
   docker compose --profile aiot --profile simulator config --quiet
   docker compose --profile aiot --profile simulator up -d --build gateway writer simulator
   docker compose logs --tail 30 writer
   ```

O worker recusa configuração vazia e qualquer bucket diferente de `telemetry_live`.
Token sem permissão não permite ACK: o original segue a política de retry/DLQ.
Não é necessário criar bucket sintético nesta tarefa: dados offline/datasets
continuam fora do bus live; eventual `telemetry_synthetic` exige autorização separada.

## Persistência e compatibilidade

`InfluxReadingRepository.save_event` reutiliza a escrita síncrona e a tradução de
erros existentes. A medição `equipment_reading_v3`, no bucket `telemetry_live`, usa:

- Tags: `event_id`, `device_id`, `device_record_id`, `environment_id`, `equipment_id`.
- Horário do ponto: primeiro `received_at` do gateway, sem gerar horário no retry.
- Campos numéricos `float`: `ambient_temperature_c`, `humidity_percent`,
  `light_percent`, `vibration_rms_mm_s`, `motor_current_a`, `motor_temperature_c`.
- Campos de identidade: `<função>_sensor_id`, `led_actuator_id`, `buzzer_actuator_id`.
- Estados booleanos: `running`, `led_actual_state`, `buzzer_actual_state`.
- Envelope preservado: `schema_version`, `occurred_at`, `received_at`, `correlation_id`.

O schema v3 fixa as unidades; nomes dos campos as tornam explícitas. Não grava
labels offline, previsões ou valores inventados. Normalizar números para `float`
evita conflito entre `60` e `60.0` aceitos pelo mesmo contrato JSON.
O cliente padrão conserva microssegundos no horário do ponto (precisão emitida
pelo gateway); strings originais de ambos os horários também ficam nos campos.

A identidade Influx é medição + tags + instante. Reentregar o mesmo evento aceito
reescreve o mesmo ponto, inclusive após reinício; eventos diferentes no mesmo
instante têm tags diferentes. Não há diário ou cache adicional no worker.
Isso depende da imutabilidade de `event_id`/primeiro aceite garantida pelo gateway;
alterar manualmente o evento e republicá-lo não é redelivery suportado.

`environment_reading` e os métodos `save/get_latest/list_history` v1/v2 permanecem
no bucket legado. Não há migração, expurgo ou regravação dos dados antigos.

## Entrega e falhas

JSON estrito UTF-8/8192 bytes, schema/formatos, unidade, tópico AMQP, metadados,
correlação, equipamento, sensores e atuadores são revalidados. Consulta SQL
parametrizada verifica dispositivo ativo → ambiente → proprietário; catálogo
comissionado continua sendo a fonte de equipamentos/sensores/atuadores.
São reutilizadas as fronteiras existentes, sem banco/catálogo novo.

ACK manual somente depois de retorno bem-sucedido da escrita síncrona. Uma queda
entre escrita e ACK pode repetir a entrega, sem criar outra leitura lógica.
Falha permanente gera `processing_error` sanitizado e rejeição sem requeue.
Falha transitória tenta até três vezes usando `x-delivery-count` e backoff quorum
existente (1 s/2 s); ao esgotar, erro `RETRY_EXHAUSTED` e DLQ privada conserva corpo
e propriedades originais. Erro usa publisher confirms/mandatory antes da rejeição;
falha dessa publicação deixa o original sem ACK. Reconexão tem espera limitada.

Parar: `docker compose stop writer`. A fila conserva mensagens enquanto parado;
iniciar novamente drena as pendências. Inspecione DLQ com identidade de auditoria
conforme [infra RabbitMQ](../infra/rabbitmq/README.md); não publique diretamente na DLX.
Não reinicie apagando volumes. Logs não incluem payload, SQL, tokens ou senhas.

## Testar

Com Python 3.13.15 e lock dev do backend instalado, na raiz:

```sh
.venv/bin/python -m pytest backend/tests/infra/test_writer_runtime.py backend/tests/repositories/test_influxdb_repository.py backend/tests/repositories/test_influxdb_client.py --cov=writer --cov=backend.app.repositories.influxdb --cov=backend.app.repositories.influxdb_client --cov-branch --cov-fail-under=80 -o addopts='' -q
COLDSAFE_WRITER_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_writer_integration.py --no-cov -o addopts='' -q
```

Integração usa projeto Docker `coldsafe-b212-*`, volumes/portas/credenciais
descartáveis e os serviços reais do Compose. Não lê `.env` pessoal. Sem opt-in,
é explicitamente skipped; mocks não contam como gravação real.

## Limites

`event_id` como tag aumenta cardinalidade por leitura. A retenção inicial de sete
dias limita dados conservados, mas não comprova capacidade nem resolve sozinha
o custo do índice. Antes de operação prolongada, medir memória/séries/latência e
revisar retenção/identidade no ensaio B2-33; não usar este bucket para milhões de
linhas sintéticas. Serviço limitado a 128 MiB/0,25 CPU, sem ensaio de carga nesta tarefa.
PostgreSQL usa a credencial existente com transação read-only, sem novo papel SQL.
Filas limitadas, broker único, três falhas/queda sucessivas e indisponibilidade
prolongada podem levar originais à DLQ; reprocessamento administrativo é explícito.
Não há transação distribuída nem promessa de exatamente uma entrega de transporte.

Semântica conferida nas fontes primárias: [identidade/duplicatas InfluxDB](https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/)
e [escrita síncrona do cliente Python](https://influxdb-client.readthedocs.io/en/stable/api.html).
