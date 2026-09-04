# Evidência TDD — validação MQTT

## Origem

Fatia derivada das tarefas CS-14 e CS-15 do Notion e do contrato
`contracts/telemetry.schema.json`.

## Jornada

Como backend do ColdSafe, quero transformar bytes MQTT não confiáveis em um modelo
validado para impedir que dados ausentes, corrompidos ou abusivos alcancem os
serviços e o InfluxDB.

## Evidência RED e GREEN

1. RED inicial: `pytest backend/tests/domain/test_telemetry.py -q` falhou com
   `ModuleNotFoundError: No module named 'backend.app'` porque a implementação ainda
   não existia.
2. GREEN inicial: o mesmo alvo passou com `29 passed` após a implementação mínima.
3. RED de segurança: o teste de tamanho falhou ao importar
   `MAX_TELEMETRY_PAYLOAD_BYTES`, ainda inexistente.
4. GREEN de segurança: o alvo passou com `30 passed` e 100% de cobertura após a
   rejeição antecipada de mensagens acima de 1 KiB.
5. A revisão acrescentou prova de que números inteiros válidos também passam pelo
   caminho real de bytes MQTT.
6. Regressão completa: `67 passed`, 100% de cobertura do código em `backend/app` e
   nenhuma dependência quebrada segundo `pip check`.

## Garantias automatizadas

| Garantia | Teste | Tipo | Resultado |
| --- | --- | --- | --- |
| Payload MQTT válido vira um modelo confiável | `test_parse_valid_mqtt_payload` | Unidade | PASS |
| Campos ausentes, extras e tipos incorretos são recusados | testes parametrizados de contrato | Unidade | PASS |
| `NaN`, infinito e valores fora dos limites são recusados | testes de medições inválidas | Unidade | PASS |
| Limites exatos do contrato são aceitos | `test_accepts_exact_technical_limits` | Unidade | PASS |
| Inteiros JSON válidos são aceitos pelo parser de bytes | teste de números inteiros | Unidade | PASS |
| JSON malformado ou incompleto é recusado | teste do parser MQTT | Unidade | PASS |
| Mensagem acima de 1 KiB é recusada antes do parse | teste de payload grande | Segurança | PASS |
| O modelo validado não pode ser alterado | `test_validated_payload_is_immutable` | Unidade | PASS |

## Cobertura e lacunas

Comando executado:

```bash
.venv/bin/python -m pytest backend/tests \
  --cov=backend/app --cov-report=term-missing --cov-fail-under=80 -q
```

Resultado: 67 testes passaram e a cobertura do código atual em `backend/app` foi
100%. Esta fatia ainda não conecta ao broker nem chama uma camada de serviço; esses
comportamentos pertencem ao ciclo de vida do assinante MQTT.

Não foram criados checkpoints Git porque o repositório inteiro ainda está sem um
commit inicial e nenhum commit foi solicitado nesta execução. A evidência RED/GREEN
foi preservada neste documento para não se perder no futuro primeiro commit.
