# Evidência TDD — assinante MQTT

## Origem

Fatia derivada da tarefa CS-18 do Notion, do contrato MQTT versionado e da
documentação oficial do Eclipse Paho para a API de callbacks v2.

## Jornada

Como backend do ColdSafe, quero manter uma assinatura MQTT durante conexões e
reconexões, validando cada mensagem antes de entregá-la ao serviço, para que dados
inválidos ou falhas transitórias não contaminem a aplicação.

## Evidência RED e GREEN

1. RED: `.venv/bin/python -m pytest backend/tests/mqtt/test_subscriber.py -q`
   falhou na coleta com `ModuleNotFoundError: No module named 'backend.app.mqtt'`.
2. GREEN inicial: o mesmo alvo passou com `20 passed` após a implementação do
   assinante e das configurações validadas.
3. Revisão de cobertura: uma ramificação de falha do pedido de assinatura foi
   identificada e ganhou uma prova dedicada.
4. A revisão de segurança encontrou que confirmação automática poderia perder uma
   mensagem quando o handler falhasse. O novo teste falhou em cinco pontos antes
   da ativação de confirmação manual.
5. GREEN final: o alvo MQTT passou com `22 passed`; a regressão completa passou
   com `104 passed`.

## Garantias automatizadas

| Garantia | Teste | Tipo | Resultado |
| --- | --- | --- | --- |
| A API de callbacks v2 e MQTT 3.1.1 são selecionados explicitamente | `test_default_client_uses_callback_api_v2` | Unidade | PASS |
| Credenciais, conexão assíncrona e loop são iniciados uma vez | `test_start_configures_credentials_connection_and_network_loop` | Unidade | PASS |
| Reconexões renovam a assinatura QoS 1 | `test_successful_connection_subscribes_again_after_reconnection` | Unidade | PASS |
| Conexão ou assinatura rejeitada é registrada sem fingir sucesso | testes de falha de conexão e assinatura | Unidade | PASS |
| Somente mensagens do tópico contratado chegam ao handler | testes de mensagem válida e tópico inesperado | Unidade | PASS |
| Payload inválido é descartado sem aparecer no log | `test_invalid_message_is_rejected_without_logging_payload` | Segurança | PASS |
| Mensagem processada é confirmada manualmente ao broker | `test_valid_message_reaches_handler_as_validated_model` | Unidade | PASS |
| Falha do handler não escapa nem confirma a mensagem | `test_handler_failure_is_contained_by_callback` | Unidade | PASS |
| Payload inválido é confirmado para impedir redelivery infinito | `test_invalid_message_is_rejected_without_logging_payload` | Segurança | PASS |
| Desligamento desconecta antes de parar o loop e é idempotente | `test_stop_disconnects_before_stopping_loop_and_is_idempotent` | Unidade | PASS |
| A senha não aparece na representação das configurações | `test_settings_do_not_expose_password_in_representation` | Segurança | PASS |

## Dependência

Foi adicionada `paho-mqtt==2.1.0`, sem dependências transitivas novas. A versão
está fixada em `backend/requirements.txt` e no lock de desenvolvimento.

## Cobertura e lacunas

Comando executado:

```bash
.venv/bin/python -m pytest backend/tests -q \
  --cov=backend/app --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Resultado: 104 testes passaram e o código atual em `backend/app` atingiu 100% de
cobertura de linhas e branches. `pip check` não encontrou dependências quebradas.

Esta fatia usa um cliente injetado nos testes para provar o ciclo de vida sem rede.
A prova com Mosquitto real, persistência e recuperação de falhas pertence à tarefa
de integração MQTT → InfluxDB → API.

Como QoS 1 permite entregas duplicadas, o próximo handler deve ser idempotente. Ele
também não deve executar trabalho lento diretamente na thread de rede; a integração
de persistência precisa manter essa fronteira explícita.

## Checkpoints Git

- RED do ciclo de vida: `c13828b`.
- RED da validação de configuração: `5e87bcb`.
- RED da criação do cliente Paho v2: `8d484bd`.
- GREEN da implementação: `fd0402f`.
- Cobertura da rejeição de assinatura: `d05919b`.
- RED da confirmação manual QoS 1: `dcf5712`.
- GREEN da confirmação após processamento: `0121bc1`.
