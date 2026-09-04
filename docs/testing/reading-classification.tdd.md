# Evidência TDD — classificação e freshness

## Origem

Fatia derivada das tarefas CS-16 e CS-17 do Notion e das regras registradas em
“02 — Arquitetura e Contratos”.

## Jornada

Como operador do laboratório acadêmico, quero que a leitura seja classificada de
forma previsível e que dados antigos tenham precedência sobre a temperatura, para
reconhecer o estado atual sem interpretar manualmente horários e limites.

## Evidência RED e GREEN

1. RED: `.venv/bin/python -m pytest backend/tests/domain/test_reading_classification.py -q`
   falhou durante a coleta com `ModuleNotFoundError` porque o módulo
   `backend.app.domain.reading_classification` ainda não existia.
2. GREEN: o mesmo alvo passou com `15 passed` após a implementação mínima.
3. Regressão e cobertura: a suíte completa passou com `82 passed` e 100% de
   cobertura de linhas e branches em `backend/app`.

## Garantias automatizadas

| Garantia | Teste | Tipo | Resultado |
| --- | --- | --- | --- |
| Temperaturas fora de 2–8 °C são críticas | `test_classifies_temperature_at_operational_boundaries` | Unidade | PASS |
| As faixas 2–2,5 °C e 7,5–8 °C, inclusive, ficam em atenção | `test_classifies_temperature_at_operational_boundaries` | Unidade | PASS |
| Temperaturas entre as margens ficam normais | `test_classifies_temperature_at_operational_boundaries` | Unidade | PASS |
| Ausência completa de leitura produz `no_data` sem freshness | `test_returns_no_data_when_no_valid_reading_exists` | Unidade | PASS |
| Exatamente 30 segundos ainda não é stale | `test_stale_takes_precedence_only_after_thirty_seconds` | Unidade | PASS |
| Após 30 segundos, stale prevalece até sobre temperatura crítica | `test_stale_takes_precedence_only_after_thirty_seconds` | Unidade | PASS |
| Resultado e freshness não podem ser alterados | `test_assessment_and_freshness_are_immutable` | Unidade | PASS |
| Leituras incompletas e horários inválidos são recusados | testes de validação temporal | Unidade | PASS |

## Cobertura e lacunas

Comando executado:

```bash
.venv/bin/python -m pytest backend/tests -q \
  --cov=backend/app --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Resultado: 82 testes passaram; 100% de linhas e branches do código atual em
`backend/app` foram cobertos.

Esta fatia classifica uma leitura já validada. A criação do horário UTC de
recebimento, a chamada durante a ingestão MQTT e a persistência do resultado ficam
para as tarefas de assinante MQTT e integração com InfluxDB.

## Checkpoints Git

- RED: `dee01ec` — `test(backend): especifica classificação de leituras`.
- GREEN: `a33f6d6` — `feat(backend): classifica estado das leituras`.
