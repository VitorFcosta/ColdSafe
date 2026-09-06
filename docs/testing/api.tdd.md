# Evidência TDD — API de monitoramento

## Escopo

Fatia correspondente às tarefas CS-22, CS-23 e CS-24: contratos REST, resumo atual,
histórico, liveness, readiness e execução do backend em container.

## RED → GREEN

1. RED: os testes falharam porque `fastapi` e `backend.app.api` não existiam.
2. GREEN: os quatro endpoints passaram com repositório, relógio e readiness
   injetáveis.
3. Hardening: falhas do cliente InfluxDB passaram a ser traduzidas para
   `503 DEPENDENCY_UNAVAILABLE`; falhas inesperadas continuam como `500` genérico.
4. RED operacional: o primeiro container falhou porque `MQTT_QOS="1"` chegava como
   texto e não era aceito por `Literal[1]`.
5. GREEN operacional: `MQTT_QOS` passou a ser inteiro restrito a 1, com teste de
   carregamento a partir de variáveis de ambiente.
6. Verificação final: 161 testes passaram com 99% de cobertura do backend.

## Garantias

- `no_data` responde 200 e não é confundido com falha.
- Freshness é recalculado na consulta; status antigo salvo não mascara `stale`.
- Histórico respeita dispositivo, período, limite, intervalo e ordem.
- Validação, dispositivo desconhecido, dependência e erro interno usam os envelopes
  e códigos previstos no OpenAPI.
- Liveness não consulta dependências; readiness verifica InfluxDB e conexão MQTT.
- O OpenAPI gerado expõe somente os quatro caminhos planejados e os códigos de
  resposta canônicos.
- O backend inicia depois das dependências saudáveis, roda como usuário não-root,
  tem filesystem somente leitura e publica a porta apenas no loopback.
- O build exclui `.env`, `.git`, `.venv`, caches e bytecode.

## Dependências adicionadas

Produção: `fastapi==0.141.1`, `uvicorn==0.52.4` e
`pydantic-settings==2.15.0`.

Desenvolvimento: `httpx==0.28.1`.

As versões diretas e transitivas estão registradas nos locks reproduzíveis.

## Prova real

Com Mosquitto, InfluxDB e backend em containers saudáveis:

1. `/health/live` e `/health/ready` responderam 200;
2. o resumo inicial respondeu `no_data`;
3. uma mensagem MQTT QoS 1 com temperatura de 8,2 °C foi publicada;
4. o resumo respondeu `critical` com a leitura persistida;
5. o histórico retornou a mesma leitura.

Nenhum commit foi criado porque isso não foi solicitado.
