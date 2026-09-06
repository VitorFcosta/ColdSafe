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
6. Regressão final: 129 testes passaram com 100% de cobertura de linhas e branches
   em `backend/app`.

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

Esta suíte prova o comportamento do adaptador com clientes injetados. A prova contra
o InfluxDB real, incluindo reinício, persistência do volume e falhas de rede, pertence
à integração MQTT → InfluxDB → API.

## Checkpoints Git

Nenhum commit foi criado porque isso não foi solicitado.
