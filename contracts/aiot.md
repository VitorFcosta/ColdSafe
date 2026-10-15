# Contrato AIoT v3 — B2-04

**Estado:** contrato definido em 12/10/2026 e revalidado em 13/10/2026; simulador MQTT v3 implementado na B2-09/10, gateway MQTT/AMQP na B2-11 e gravador InfluxDB na B2-12;
API e demais consumidores de negócio v3 ainda não implementados. A aplicação continua v1/v2. Este documento fecha as fronteiras
do plano aprovado; não comprova integração completa, IA ou 3D. Evidências por tarefa ficam nos cartões.

Fonte estrutural: [aiot.schema.json](aiot.schema.json), JSON Schema Draft 2020-12,
com referências locais. Regras relacionais deste documento são obrigatórias:
JSON Schema sozinho não verifica banco, autorização, tópico ou outra mensagem.
Os testes em `backend/tests/contract/test_aiot_contract.py` conferem exemplos e
essas relações usando um catálogo fictício, sem substituir validação em produção.

Referências: [tarefa B2-04](../docs/aiot/tasks/B2-04.md),
[plano aprovado](../docs/aiot/plan.md),
[arquitetura alvo](../docs/aiot/architecture.md).

## Identidades, unidades e estado real

O alvo é um ventilador de refrigeração. `environment_id`, `device_record_id`,
`equipment_id`, `sensor_id` e `actuator_id` são UUIDs do catálogo, escritos em
minúsculas. `device_id` é a identidade MQTT existente, até 64 caracteres
`A–Z a–z 0–9 . _ -`; não é o UUID do dispositivo. Exemplo válido: `esp32.lab-01`.
O cadastro deve vincular dispositivo → ambiente privado → proprietário e
equipamento → sensores/atuadores; o gateway verifica todos esses vínculos.
Na B2-11, os primeiros vêm do PostgreSQL; equipamento/sensores/atuadores são
conferidos no catálogo privado de comissionamento, sem tabelas/API dessas entidades.
IDs enviados pelo equipamento nunca são autoridade de propriedade.

As seis funções são chaves fixas em `data.measurements`; cada valor contém
`sensor_id`, `unit` e `value`. Os IDs vêm do cadastro, não de um enum de nomes.
Um sensor não pode ocupar duas funções. Ambiente e motor não são intercambiáveis,
mesmo medidos em graus Celsius; o catálogo identifica qual ID ocupa cada função.

| Função / chave live | Unidade no JSON | Grandeza | Intervalo live v3 |
| --- | --- | --- | --- |
| `ambient_temperature` | `degC` | Temperatura do ambiente refrigerado | −40 a 80 |
| `humidity` | `percent` | Umidade relativa | 0 a 100 |
| `light` | `percent` | Luminosidade relativa calibrada; não lux | 0 a 100 |
| `vibration` | `mm/s` | Velocidade de vibração RMS | 0 a 100 |
| `motor_current` | `A` | Corrente RMS do motor | 0 a 100 |
| `motor_temperature` | `degC` | Temperatura do motor | −40 a 200 |

Limites de vibração, corrente e motor são limites técnicos iniciais do contrato
de simulação, não faixas seguras industriais nem limiares de alerta. Calibração,
perfil de operação, janela RMS e limites de alerta pertencem à implementação e
configuração do simulador/sensores. Alterar unidades ou interpretação exige
versão nova; nunca reinterpretar o histórico.

`data.equipment` contém `equipment_id` e `running` booleano.
`data.actuators.led` e `buzzer` contêm `actuator_id` e `actual_state` booleano.
São estados recebidos do equipamento, separados de pedidos e previsões.
`running` não cria um comando manual para o ventilador. LED continua manual;
buzzer continua automático. Posições 3D pertencem ao frontend; IDs são os mesmos
do catálogo, sem inferir saúde individual de sensores sem modelo.

## Envelope e confiança no horário

Todo evento tem exatamente estes campos:

| Campo | Regra |
| --- | --- |
| `schema_version` | Inteiro 3 |
| `event_id` | UUID estável de um evento lógico |
| `type` | Tipo fechado, com `data` específico |
| `occurred_at` | Instante do produtor em UTC, terminado em `Z` ou `+00:00` |
| `received_at` | Primeiro aceite por gateway/API confiável; UTC ou nulo só na borda |
| `device_id` | Identidade MQTT ou nulo no escopo de job/modelo |
| `device_record_id` | UUID do dispositivo ou nulo no escopo de job/modelo |
| `environment_id` | UUID do ambiente privado, quando aplicável |
| `correlation_id` | UUID da operação que liga eventos relacionados |
| `data` | Objeto fechado conforme `type` |

`telemetry`, `command`, `ack`, `command_status`, `prediction`, `alert` e
`freshness` exigem as três identidades de escopo não nulas.
Jobs/modelos têm os dois IDs de dispositivo nulos; ambiente pode ser nulo.
Mesmo sem ambiente, job/modelo tem proprietário no registro privado do PostgreSQL;
nulo nunca significa transmissão pública. `processing_error` aceita as três
identidades preenchidas ou as três nulas, sem combinação parcial.

No MQTT, telemetria e ACK chegam com `received_at=null`. O gateway resolve
identidade, valida e preenche esse campo uma única vez. Comandos já nascem na API
confiável com horário de aceite. Todo evento no RabbitMQ exige `received_at`
não nulo. O relógio do equipamento não decide freshness nem a ordem de aceite.
Uma duplicata preserva `event_id` e o primeiro `received_at`, inclusive em retry;
o consumidor deduplica por `(consumer, event_id)`. Correlação não é deduplicação:
vários eventos legítimos compartilham uma operação.

JSON estrito UTF-8, no máximo **8192 bytes por evento v3** em cada fronteira,
antes de decodificar. Valores numéricos finitos; rejeitar `NaN` e infinitos,
inclusive constantes aceitas por parsers permissivos. Campos extras são
rejeitados em todos os objetos, inclusive labels escondidos em `data`.
Ativar `FormatChecker` ao validar UTC/UUID com python-jsonschema.
O limite antigo v1/v2 permanece; este limite v3 não altera o parser atual.

## Transporte e responsabilidade

MQTT: QoS 1, `retain=false`, identidade/ACL por dispositivo, tópico igual ao
payload; só o gateway publica comandos no fluxo v3.

| Tópico | Publicador | Recebedor |
| --- | --- | --- |
| `coldsafe/v3/devices/{device_id}/telemetry` | Equipamento/simulador | Gateway |
| `coldsafe/v3/devices/{device_id}/commands` | Gateway após autorização da API | Equipamento/simulador |
| `coldsafe/v3/devices/{device_id}/acks` | Equipamento/simulador | Gateway |

Simulador B2-09: implementação e cadastro local de comissionamento em
[`simulator/README.md`](../simulator/README.md). A ACL provisiona `sim-lab-01`
com credencial própria para telemetria/ACK e leitura de comandos implementados
na B2-10; o [gateway B2-11](../gateway/README.md) liga MQTT ao AMQP, e consumidores de negócio continuam posteriores. Iniciar/parar **a simulação** e injetar falha usam o tópico
operacional separado `coldsafe/simulator/devices/sim-lab-01/control`, fora do
envelope v3: somente a credencial confiável `coldsafe-simulator-operator` publica.
Formato fechado e prazo de 30 s estão no README do simulador. Não é comando
manual do ventilador, não entra em AMQP e não substitui autorização da API.
O cadastro local valida IDs/funções; o gateway confere dispositivo ativo, ambiente
e proprietário esperado no PostgreSQL, sem inferir propriedade de IDs recebidos.

RabbitMQ: exchange topic durável `coldsafe.events`, mensagens persistentes,
confirmação de publicação, ACK manual após efeito durável/idempotente.

| Tipos | Routing key | Quem origina / responsabilidade |
| --- | --- | --- |
| `telemetry`, `ack` | `v3.{type}.{device_record_id}` | Gateway após validação; gravação/inferência/comandos recebem |
| `command` | `v3.command.{device_record_id}` | API/regra autorizada; gateway traduz para MQTT |
| `command_status`, `alert`, `freshness` | `v3.{type}.{device_record_id}` | Serviço de comandos/regras/estado; entrega autorizada |
| `prediction` | `v3.prediction.{device_record_id}` | Inferência; regras e entrega recebem |
| `job_requested`, `job_progress` | `v3.{type}.{data.job_id}` | API privada / worker de geração ou treino |
| `model_activation`, `model_status` | `v3.{type}.{data.model_id}` | API autorizada / serviço de inferência |
| `processing_error` | `v3.processing_error.{correlation_id}` | Consumidor que detecta falha; auditoria/DLQ |

Usar UUID na routing key evita que o ponto permitido em `device_id` vire um
segmento RabbitMQ. O consumidor valida routing key e catálogo, além do schema.
Gravação persiste leituras no InfluxDB; metadados, comandos, alertas, auditoria,
jobs e registro de modelos ficam no PostgreSQL; datasets ficam separados.
Nomes físicos, bindings e credenciais foram implementados na B2-07;
[infra RabbitMQ](../infra/rabbitmq/README.md) descreve a topologia executável.
Gateway já produz telemetria/ACK e consome comandos; o [gravador B2-12](../writer/README.md)
consome sua fila de telemetria e persiste seis sensores/estados no bucket `telemetry_live`,
sem modificar o histórico legado. Demais produtores/consumidores v3 continuam planejados. Para separar geração
de treino sem alterar a routing key, o publicador de `job_requested` copia
`data.job_type` para o header AMQP `job_type`; o consumidor exige igualdade.
Esse header é metadado de transporte, fora do envelope JSON.

O backend verifica sessão revogável e propriedade antes de consulta, comando,
assinatura e cada envio. O navegador não acessa MQTT, AMQP ou bancos.
Observabilidade tem consumidor próprio; não retira mensagens das filas de trabalho.
REST recupera estado/histórico ao conectar e reconectar; WebSocket entrega
eventos já processados, respeitando a ordenação/persistência necessária de cada
consumidor. O stream v3 deverá ser separado ou negociado explicitamente; não
enviar v3 no stream atual `/api/v1/events`, cujo cliente aceita v2.
Endpoints e tipos Pydantic/TypeScript serão implementados junto dos consumidores.

## Telemetria, previsão e freshness

A telemetria usa `correlation_id=event_id`.
Previsão contém `equipment_id`, `source_event_id`, `input_received_at`,
`features_version`, `model_id`, `model_version`, `status`, `health_score`,
`rul_hours` e `reason`. Fonte, correlação, equipamento, dispositivo, ambiente e
horário de entrada devem coincidir com a telemetria aceita.

| Previsão | Saúde / RUL | Modelo e motivo |
| --- | --- | --- |
| `available` | Saúde 0–100; RUL em horas ≥0 | ID/versão carregados; `reason=null` |
| `unavailable` | Ambos nulos | Motivo obrigatório; modelo nulo quando não existe |

Motivos: `no_model`, `insufficient_history`, `invalid_features`,
`model_unavailable`, `stale_input`. Não misturar uma saída válida com outra
ausente. ID e versão do modelo ficam nulos juntos; `no_model` exige ambos nulos.
Zero é um valor válido, não marcador de indisponibilidade.
`features_version` identifica ordem, unidades, transformações e janelas
compartilhadas entre treino e online; o pacote registrado descreve esse layout.
Apenas janelas passadas; nada de labels ou dados futuros como features.

A interface correlaciona por `source_event_id` e escopo. Previsão atrasada pode
ficar no histórico, mas não se torna previsão da leitura mais nova.
Uma previsão não renova o horário da telemetria. Validar freshness também no
consumidor; emitir `stale_input` quando a entrada já expirou.
No relógio confiável do serviço, a previsão não pode preceder o aceite da entrada;
`available` exige idade de entrada até 30 segundos, e `stale_input` exige mais de
30 segundos. Alertas preditivos também verificam essa idade ao avaliar a previsão.

`freshness.data` contém `last_event_id`, `last_received_at`, `state`,
`age_seconds` e `stale_after_seconds=30`. O serviço calcula idade no instante
`occurred_at` do evento: até **30 segundos inclusive** é `fresh`; acima, `stale`.
`no_data` tem ID, horário e idade nulos. Antes da primeira leitura, não inventar
zero nem estado normal. O frontend continua aumentando a idade pelo tempo
monotônico desde a última atualização; se o stream parar, congela giro/tremor da
cena e sinaliza stale. Estado real recebido continua histórico, não confirmação nova.

Alertas têm ID, equipamento, tipo, estado aberto/fechado e evento fonte.
A fonte é telemetria para temperatura ou previsão disponível/fresca para saúde/RUL;
o escopo e a correlação acompanham a fonte. Temperatura de refrigeração usa o
sensor ambiente, sem confundir motor. A regra mantém o ponto inicial aprovado
de 3 previsões críticas para abrir e 10 recuperadas para limpar, com limiares
configurados e explícitos. Ausência, atraso ou indisponibilidade não limpam alerta
nem acionam uma recuperação fictícia; a máquina de estados será testada no runtime.

## Comando explícito e ACK

`command.data` contém comando/atuador UUID, `actuator`, `desired_state`,
`source` e `deadline_at`. `true` liga e `false` desliga; nunca usar toggle.
Pares permitidos: `led/manual` e `buzzer/automatic`. Prazo é
`occurred_at + 30 segundos`; o serviço recusa atuação após o prazo.
Comando, ACK e mudanças de status usam `correlation_id=command_id`.

ACK informa comando e atuador, `result`, `applied_state` e `reason`.
`applied` exige estado booleano e motivo nulo; `rejected` exige estado nulo e
motivo `INVALID_COMMAND`, `ACTUATOR_FAILURE` ou `EXPIRED_COMMAND`.
Aceitar somente vínculo com um comando autorizado do mesmo dispositivo/atuador.
Um ACK que relata estado diferente do desejado é válido como relato de falha:
o serviço marca `rejected`, não transforma o relato em sucesso.

Status: `pending` antes de publicar; `confirmed` só por ACK válido no prazo e
estado igual ao desejado; `rejected` por rejeição/divergência; `unconfirmed`
quando expira ou não pode ser entregue. Apenas `confirmed` tem
`confirmed_state` booleano igual ao desejado; os demais usam nulo.
ACK tardio fica auditável e não muda silenciosamente um timeout para sucesso.
Deduplicação evita repetir atuação; publicar no broker nunca confirma atuação.

O prazo usa `received_at` confiável do ACK, nunca `occurred_at` do equipamento.
Para justificar `confirmed`, o ACK precisa ser recebido entre o aceite do comando
e `deadline_at`, inclusive; o status não pode ser emitido antes desse recebimento.
Processar um ACK recebido no prazo depois do deadline não autoriza reverter um
timeout já persistido; essa transição dependerá do estado durável no runtime.

A B2-10 implementa a borda no [simulador](../simulator/README.md): LED/manual
altera luminosidade, buzzer/automatic altera estado, comandos explícitos validam
cadastro local/prazo/identidades e geram ACK por MQTT. Só `coldsafe-gateway`
publica comandos; `sim-lab-01` publica ACK. A credencial MQTT do gateway é
separada da AMQP; a B2-11 implementa a ponte em serviço próprio.
Duplicata idêntica no prazo reutiliza o ACK sem reaplicar; expirado recebe
rejeição. JSON/IDs/escopo sem identidade segura não geram ACK inventado.
Cache e estados são em memória, limitados a 256 comandos por processo; restart
reinicia ambos. Gateway B2-11 mantém deduplicação/saídas/erros no diário SQLite e
valida propriedade PostgreSQL. Status/timeout durável, autorização HTTP v3 e
consumidores de negócio continuam posteriores; cache do simulador segue em memória.

## Jobs e ativação de modelos

`job_requested` carrega `job_id`, `job_type=generation|training` e
`dataset_id` (nulo para geração, UUID para treino). A configuração validada e
seu dono ficam no registro privado do job; o worker resolve esse registro pelo ID,
sem confiar em caminho ou configuração livre enviados pelo broker.
Este evento não define a futura API inteira do Laboratório.

`job_progress` usa o mesmo job/correlação, estado `queued|running|completed|
failed|cancelled`, contadores inteiros, `result_id` e `error_code`.
Contadores: `0 ≤ completed_units ≤ total_units`, total positivo; queued começa
em zero; completed exige igualdade e resultado UUID persistido.
Nos demais estados resultado é nulo; failed exige `GENERATION_FAILED` ou
`TRAINING_FAILED`, correspondente ao tipo do job; nos outros o erro é nulo.
Progresso preserva o tipo, ID e escopo da solicitação. Unidade: linhas na geração e
modelos concluídos no treino (2 regressões). Percentual deriva dos contadores.
Estados terminais não voltam a running por duplicata; atualizar progresso só
após checkpoint do trabalho. Geração em blocos no disco, ≥1 milhão e teto inicial
2 milhões condicionado à capacidade; o contrato não comprova essa execução.

`model_id/model_version` identificam o pacote com as duas regressões separadas
(saúde e RUL), seus metadados e features, não um LLM.
Ativação tem `activation_id`, modelo/versão/features e modelo anterior ativo;
`correlation_id=activation_id`. Serviço carrega só artefato interno registrado,
compatível e aprovado, sem caminhos/URLs arbitrários nem desserialização pública.
Troca é atômica para o pacote completo. `model_status` referencia essa ativação:
ready/loading sem erro, active com `active_model_id=model_id`, failed com
`MODEL_LOAD_FAILED` e o ID anterior preservado, inclusive nulo se não existia.
A versão e o layout de features devem coincidir com a solicitação de ativação;
ready/loading preservam o modelo anterior até a troca atômica. Serializar
ativações por escopo de modelo e revalidar a versão anterior no registro privado
evita que solicitações concorrentes restaurem uma versão já substituída.
A versão realmente carregada aparece em cada previsão; publicar ativação
não significa que já foi ativada. Falha preserva o serviço anterior.

## Erro e retry

`processing_error` contém evento fonte conhecido (ou nulo), código fechado,
`retryable` e `attempt` de 1 a 3, sem payload bruto, segredo, caminho ou stack.
`INVALID_SCHEMA`, `INVALID_BINDING`, `IDENTITY_MISMATCH`,
`UNAUTHORIZED_SCOPE` e `PAYLOAD_TOO_LARGE` são permanentes: sem retry.
`PROCESSING_FAILED` permite retry de falha transitória, com backoff limitado;
tentativa é metadado da execução, sem alterar o evento original.
Ao esgotar 3 tentativas, `RETRY_EXHAUSTED`, sem retry, e DLQ privada.
Na tentativa 3 nunca sinalizar outro retry; `RETRY_EXHAUSTED` exige tentativa 3.
Eventos de erro têm IDs próprios; o original preserva sua identidade.

Não tentar encaminhar ao WebSocket um evento inválido sem escopo confiável.
DLQ/auditoria privada guarda o original e contexto de falha com acesso restrito;
a amostra pública/autorizada usa somente o erro sanitizado. Usuário autenticado
não ganha acesso a erro ou job de outro proprietário só porque conhece um UUID.

## Labels exclusivamente offline

Validar dados offline com `#/$defs/offline_row`, fora de `event`, MQTT e AMQP.
Linha lógica contém versão, dataset/equipamento UUID, horário observado, seis
medições com nomes e unidades explícitos e `labels`.

Medições offline: `ambient_temperature_c`, `humidity_percent`, `light_percent`,
`vibration_rms_mm_s`, `motor_current_a`, `motor_temperature_c`.
Aceitam números finitos e nulos para faltantes; outliers podem exceder os limites
live. Esse schema descreve uma linha lógica, não obriga serializar milhões de
linhas JSON: armazenamento NumPy por blocos é decisão da tarefa de geração.

Labels: `health_score_true` 0–100, `rul_hours_true` ≥0 ou nulo e
`rul_observed` booleano. Se false, RUL é nulo (censura); se true, RUL é numérico,
inclusive zero quando a falha foi observada. Equipamento sem falha observada
não recebe RUL zero. Separar equipamentos entre conjuntos antes de ajustar
transformações; nenhuma dessas verdades aparece em telemetria, previsão ou 3D.

## Compatibilidade e três fluxos revisáveis

1. **Monitoramento:** `telemetry_edge` → gateway valida catálogo/tópico e preenche
   aceite → `telemetry_received` → gravação/inferência → previsão vinculada →
   alerta/freshness → entrega privada. Exemplos `prediction_available_zero_rul`
   e `prediction_unavailable_no_model` distinguem zero real de ausência.
2. **Atuação:** API autentica/propriedade → `command` LED explícito →
   gateway/MQTT → ACK → status confirmado/rejeitado ou timeout auditável.
   Exemplos incluem buzzer automático e ACK com estado divergente.
3. **Laboratório:** API registra job privado → solicitação → progresso/resultado
   persistido → ativação de candidato aprovado → estado ativo ou falha com
   modelo anterior preservado. Labels ficam no dataset offline.

Esses são fluxos contratuais; implementação e ensaio integrado ficam nas tarefas
correspondentes. `aiot.valid.json` contém exemplos completos, `aiot.context.json`
o catálogo fictício e `aiot.invalid.json` mutações explícitas (`base/set/remove`
e transporte opcional). O teste materializa cada mutação antes de validar, e a
categoria esperada distingue formato, vínculo, semântica e catálogo.
`reference` liga ACK/status ao comando e previsão à telemetria aceita.
Status confirmado também usa `ack_reference` para indicar a prova de atuação;
esses dois campos são metadados dos exemplos, fora do payload transmitido.
Os exemplos distinguem ACK no limite de 30 segundos, tardio e divergente:
os dois últimos são relatos auditáveis, mas não justificam confirmação.

Não alterar `telemetry.schema.json`, `evolution.schema.json` ou seus exemplos.
MQTT v1/v2 e HTTP/OpenAPI atuais mantêm formato e semântica. Histórico v1 mantém
luminosidade nula; nunca inventar vibração/corrente/motor/saúde/RUL para dados
antigos. Ao projetar histórico antigo no novo domínio, ausência é nula com
proveniência da versão; não emitir uma telemetria v3 incompleta como se fosse live.

O rollout exige habilitar produtor e consumidores compatíveis antes de ativar
v3, migrações aditivas e transição coordenada de ACLs/streams; não substituir
v1/v2 silenciosamente. Não publicar a mesma leitura em versões diferentes como
leituras novas sem uma estratégia explícita de identidade na migração.
Campos extras são incompatíveis dentro desta versão fechada; mudanças de
formato/unidade/semântica exigem nova versão e novos testes.

## Verificação desta entrega

```sh
.venv/bin/python -m pytest backend/tests/contract -q --no-cov -o addopts=''
```

Essa rodada verifica contrato sem atribuir cobertura do runtime a schemas.
Os testes antigos de v1/v2/OpenAPI continuam parte da regressão.
Se imports da pasta Documents travarem, usar snapshot do HEAD mais estes arquivos
em diretório local temporário, com as mesmas versões de
`backend/requirements-dev.lock.txt`; registrar hashes e limitação no checkpoint.
Não usar sucesso de testes de exemplos como prova de autorização real, atuação
física, qualidade de modelos ou integração da arquitetura alvo.
