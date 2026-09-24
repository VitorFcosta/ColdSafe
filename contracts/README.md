# Contratos compartilhados

Esta pasta é a fonte técnica de verdade para as fronteiras do ColdSafe.

- `telemetry.schema.json`: telemetria **v1 em produção no protótipo atual**.
- `openapi.yaml`: contrato HTTP **v1 completo**, incluindo contas, ambientes,
  dispositivos, limites, monitoramento e saúde; deve acompanhar `/openapi.json`.
- `evolution.schema.json`: formatos **propostos** para a evolução, ainda sem implementação no runtime.
- `examples/`: mensagens válidas e inválidas verificadas pelos testes de contrato.

Uma mudança de formato deve começar aqui e nos testes de contrato antes de chegar aos produtores ou consumidores.

## Estado atual e versões

Hoje o ESP32 publica temperatura e umidade em `coldsafe/v1/telemetry`, e o backend aceita somente esse tópico. O HTTP v1 já oferece cadastro, sessão revogável, ambientes, dispositivos e limites, além das consultas por dispositivo com autorização por propriedade. A rota legada do dispositivo fixo permanece pública somente enquanto ele não tiver proprietário. A documentação de evolução abaixo **não significa que telemetria v2, comandos, WebSocket ou interface de login já existam**. O contrato v1 e os volumes de InfluxDB permanecem intactos durante a migração.

O campo `schema_version` versiona o formato da mensagem, enquanto o segmento `v2` versiona os novos tópicos MQTT. Mensagens v1 continuam válidas apenas no tópico v1; mensagens v2 incluem `light_percent` e usam os novos tópicos. Não aceitar uma v1 como v2 preenchendo luminosidade artificialmente.

## MQTT planejado

| Tópico | Quem publica | Quem recebe | Conteúdo |
| --- | --- | --- | --- |
| `coldsafe/v2/devices/{device_id}/telemetry` | ESP32 correspondente | Backend | `telemetry` |
| `coldsafe/v2/devices/{device_id}/commands` | Backend | ESP32 correspondente | `command` |
| `coldsafe/v2/devices/{device_id}/acks` | ESP32 correspondente | Backend | `ack` |

Usar QoS 1, mensagens não retidas e `device_id` igual no tópico e no payload. A identidade MQTT de cada ESP32 deve ter permissões do broker somente para publicar sua telemetria e suas confirmações e assinar seus comandos; nunca usar um mesmo client ID para dois dispositivos. O backend é o único publicador de comandos. A publicação MQTT significa apenas entrega ao broker, não atuação confirmada. O broker valida a identidade e as permissões; o backend valida dispositivo cadastrado, limites físicos, versão, tópico e tamanho antes de gravar ou atuar.

`light_percent` é brilho relativo calibrado entre 0 (escuro) e 100 (claro), não lux. A calibração do sensor real/simulado fica no firmware; valores fora de 0–100 ou medições inválidas não são publicados. `received_at` é criado pelo backend em UTC, pois o ESP32 não é autoridade de horário.

### Comandos e confirmações

`command_id` (UUID) correlaciona um comando à confirmação. `desired_state` e `applied_state` são booleanos: `true` liga, `false` desliga. Controle manual alcança somente o LED; a regra automática alcança somente o buzzer. O backend registra o comando como `pending` antes de publicar e aplica prazo de **10 segundos**. Aceita `ack` somente se dispositivo, atuador e `command_id` coincidirem com um comando pendente; confirma `confirmed` apenas se `result=applied` e `applied_state=desired_state`. Rejeição ou estado divergente vira `rejected`. Sem confirmação válida no prazo, fica `unconfirmed` e `confirmed_state=null`; um `ack` tardio fica auditável, sem transformar silenciosamente um prazo vencido em sucesso. Duplicatas de QoS 1 não repetem a atuação nem criam comandos novos.

Resposta REST proposta para solicitar comando: envelope `{ "success": true, "data": <command_response>, "meta": { "schema_version": 2 } }`. A resposta inicial é `pending`; a consulta autenticada de estado pode retornar `pending`, `confirmed`, `rejected` ou `unconfirmed`. O dashboard mostra separadamente o estado desejado e o último confirmado, inclusive ao reconectar. A rota e os códigos HTTP dessa futura API devem entrar no OpenAPI quando forem implementados; `openapi.yaml` continua descrevendo apenas a API atual.

## WebSocket planejado

O backend envia eventos `reading`, `alert` e `command_status` conforme `ws_event` em `evolution.schema.json`. Cada evento informa `environment_id`, `device_id`, `occurred_at` em UTC e o dado tipado. O backend envia uma leitura somente **após** validá-la e persistí-la. WebSocket serve para atualização em tempo real; ao conectar ou reconectar, o cliente usa REST autenticado para recuperar estado e histórico, pois pode ter perdido eventos. Não confiar em um ID vindo do cliente para autorizar a assinatura.

## Isolamento por usuário

Antes de cada consulta REST, criação de comando ou assinatura WebSocket, resolver a sessão revogável e verificar no PostgreSQL que o ambiente e o dispositivo pertencem ao usuário. Um identificador válido de outra conta não concede acesso; a API deve recusar a operação sem revelar leituras, alertas ou estado do atuador. No WebSocket, validar propriedade na conexão e antes de cada envio, encerrar a conexão quando a sessão expirar ou for revogada e nunca transmitir eventos entre usuários. Não receber comandos diretamente pelo WebSocket. O backend, não o navegador, publica no MQTT após autorização. A identidade MQTT do ESP32 não substitui a sessão do usuário.

Exemplo de tentativa **inválida por autorização**, embora o formato JSON seja válido: usuário A envia pedido para ligar `esp32-lab-02`, pertencente ao usuário B. O backend recusa antes de publicar no MQTT e não retorna estado de B. Essa regra depende do banco e da sessão e, portanto, não pode ser expressa só por JSON Schema.

## Histórico e fluxo completo

Leituras antigas ficam no InfluxDB com temperatura e umidade. Nas respostas futuras de histórico, manter `schema_version: 1` e projetar `light_percent: null` para leituras v1; `null` significa que a luminosidade não foi coletada, nunca zero. Leituras v2 têm luminosidade numérica. Não apagar nem regravar dados antigos. O HTTP v1 atual mantém sua forma sem `light_percent`; a nova projeção deve ser exposta em contrato de API versionado quando o runtime correspondente existir.

1. Sensor → ESP32 publica `telemetry` v2 no tópico próprio → broker valida identidade e backend valida dispositivo, tópico e payload → InfluxDB armazena a leitura → backend emite `reading` apenas aos usuários proprietários.
2. Web autenticada → REST solicita o LED → backend valida propriedade, cria `pending` e publica `command` → ESP32 atua e publica `ack` → backend correlaciona e grava `confirmed`/`rejected`, ou marca `unconfirmed` após 10 segundos → WebSocket informa a mudança ao proprietário; REST recupera o estado após reconexão.

Os exemplos em `examples/evolution.valid.json` e `examples/evolution.invalid.json` cobrem formatos MQTT, resposta REST, eventos WebSocket e histórico antigo. Os testes de contrato verificam os JSON Schemas e a separação dos tópicos; a autorização e os fluxos reais exigirão testes de integração nas tarefas de implementação.
