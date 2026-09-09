# Evidência TDD — repositório InfluxDB

## Origem

Fatia derivada das tarefas CS-19 e CS-20 do Notion e das decisões registradas em
“05 — Backend e Dados”.

## Jornada

Como backend do ColdSafe, quero persistir leituras validadas e consultar a leitura
mais recente e o histórico por dispositivo, para que a API possa responder sem
conhecer detalhes do InfluxDB.

## Evidência RED e GREEN

1. RED: `.venv/bin/python -m pytest backend/tests/repositories/test_influxdb_repository.py -q`
   falhou durante a coleta com `ModuleNotFoundError` porque o pacote
   `backend.app.repositories` ainda não existia.
2. GREEN inicial: o alvo do repositório passou com 7 testes após a implementação
   mínima de escrita, leitura atual e histórico.
3. Revisão independente: foram identificados parâmetros Flux referenciados de forma
   incorreta, limite aplicado por grupo de tags e ausência de validação temporal.
4. GREEN final: os parâmetros passaram a ser vinculados diretamente, as séries são
   agrupadas antes de ordenar e limitar, e horários válidos são normalizados para UTC.
5. Hardening de segurança: um teste adicional provou que URLs com query string ou
   fragmento eram aceitas; a configuração passou a rejeitá-las para impedir que
   segredos apareçam na representação da URL.
6. Integração real: o primeiro teste revelou que o InfluxDB 2.7.12 rejeitava o nome
   `row` no parâmetro das funções Flux; a troca mínima para `r` corrigiu as consultas.
7. Regressão final: 136 testes passaram com 100% de cobertura em `backend/app`.

## Garantias automatizadas

| Garantia | Tipo | Resultado |
| --- | --- | --- |
| Leitura validada é escrita com tags, fields e horário UTC esperados | Unidade | PASS |
| Horário com fuso é normalizado para UTC | Unidade | PASS |
| Horário sem fuso é rejeitado | Unidade | PASS |
| Ausência de leitura atual retorna `None` | Unidade | PASS |
| Resultado do InfluxDB é convertido em objeto imutável | Unidade | PASS |
| `device_id` é enviado como parâmetro, sem interpolação na consulta Flux | Segurança | PASS |
| Token é omitido das representações e a URL rejeita credenciais, query e fragmento | Segurança | PASS |
| Histórico respeita intervalo, limite global e ordem cronológica | Unidade | PASS |
| Limites fora de 1–1000 e intervalo temporal inválido são rejeitados | Unidade | PASS |
| Fábrica força escrita síncrona e fecha os recursos mesmo após falha parcial | Unidade | PASS |
| Escrita, leitura atual e histórico funcionam no InfluxDB 2.7.12 real | Integração | PASS |
| MQTT QoS 1 percorre validação, classificação e persistência real | Integração | PASS |

## Decisões de persistência

- Measurement: `environment_reading`.
- Tags: `device_id` e `status`, usadas em filtros com cardinalidade controlada.
- Fields: `schema_version`, `temperature_c` e `humidity_percent`.
- Timestamp: `received_at`, fornecido pelo backend e normalizado para UTC.
- Resultados de histórico são tuplas para não expor uma coleção mutável.
- O cliente é injetado por interfaces mínimas, mantendo os testes sem rede.

## Dependências e lacunas

Foi adicionada a dependência `influxdb-client==1.50.0` em `backend/requirements.txt`
e no lock de desenvolvimento. A fábrica do cliente real usa escrita síncrona para
que a confirmação manual do MQTT não ocorra antes da persistência.

Nenhuma dependência adicional foi necessária para a integração: `pytest`,
`paho-mqtt` e `influxdb-client` já faziam parte do lock.

O arquivo `compose.integration.yaml` publica o InfluxDB apenas em
`127.0.0.1:18086`, exclusivamente durante a verificação local. O Compose normal
continua sem expor o banco.

Para executar a prova com uma pilha descartável, defina credenciais locais no
ambiente e use:

```bash
docker compose -p coldsafe-integration \
  -f compose.yaml -f compose.integration.yaml up -d --wait

INFLUXDB_TEST_URL=http://127.0.0.1:18086 \
INFLUXDB_TEST_ORG="$DOCKER_INFLUXDB_INIT_ORG" \
INFLUXDB_TEST_BUCKET="$DOCKER_INFLUXDB_INIT_BUCKET" \
INFLUXDB_TEST_TOKEN="$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
MQTT_TEST_HOST=127.0.0.1 \
MQTT_TEST_PORT=1883 \
MQTT_TEST_BACKEND_PASSWORD="$MQTT_BACKEND_PASSWORD" \
MQTT_TEST_DEVICE_PASSWORD="$MQTT_DEVICE_PASSWORD" \
API_TEST_URL=http://127.0.0.1:8000 \
.venv/bin/python -m pytest -m integration -q
```

O teste de pipeline publica uma leitura MQTT controlada e confirma que ela aparece
no resumo atual e no histórico expostos pela API. A prova de reinício do volume
permanece para uma tarefa de QA posterior.

## Checkpoints Git

Nenhum commit foi criado porque isso não foi solicitado.
