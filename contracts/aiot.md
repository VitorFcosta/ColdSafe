# Contrato AIoT v3 — B2-04

**Estado:** contrato definido em 12/10/2026 e revalidado em 13/10/2026; simulador MQTT v3 implementado na B2-09/10, gateway MQTT/AMQP na B2-11 e gravador InfluxDB na B2-12;
API, regras de temperatura e entrega privada v3 implementadas na B2-13;
dashboard e inferência continuam posteriores. O fluxo v1/v2 é preservado. Este documento fecha as fronteiras
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
O resumo autenticado expõe somente para leitura os IDs desse catálogo em
`inventory`, após validar dispositivo ativo e proprietário atual no PostgreSQL.
Isso não cria cadastro editável nem acrescenta coordenadas 3D ao contrato.

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
na B2-10; o [gateway B2-11](../gateway/README.md) liga MQTT ao AMQP, e a API B2-13
processa regras/entrega. Iniciar/parar **a simulação** e injetar falha usam o tópico
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
| `telemetry_persisted` | `v3.telemetry_persisted.{device_record_id}` | Gravador após escrita; regras/entrega recebem prova da gravação |
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
sem modificar o histórico legado. A API B2-13 usa `commands`/`delivery`, com
credenciais distintas; comando v3 sai somente por AMQP. Demais consumidores
continuam planejados. Para separar geração
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
As rotas v3 da B2-13 estão abaixo; integração TypeScript pertence à B2-14.

### Persistência e recuperação HTTP v3 — B2-13

`telemetry_persisted.data` contém `source_event_id`, `equipment_id` e
`input_received_at`, iguais à fonte gravada; escopo e correlação coincidem.
Writer publica com confirmação após escrita síncrona e antes do ACK da fonte.
Cada gravação/regravação concluída gera recibo com UUID próprio e horários reais;
a telemetria conserva identidade e primeiro aceite. Recibos repetidos não geram
novas leituras nem repetem regras.

Fonte, recibo e previsão são guardados independentemente da ordem de chegada.
WebSocket exige fonte persistida e vínculos validados. Regras deduplicadas,
comandos, auditoria e outbox são confirmados numa transação PostgreSQL.
Saídas próprias entregues correspondem ao envelope durável da outbox.
Publicar comando no broker não comprova atuação: somente ACK válido confirma.

| Rota | Comportamento |
| --- | --- |
| `GET /api/v3/monitoring/summary?device_id=...` | Estado processado da conta, inclusive com gravador atrasado |
| `GET /api/v3/readings?device_id=...&period=1h&limit=300` | Histórico processado, mais recente primeiro, limite 1–1000 |
| `GET /api/v3/alerts?device_id=...` | Intervalos de alertas privados, limite 1–1000 |
| `GET /api/v3/commands/{command_id}` | Status durável do próprio comando, inclusive após reconexão |
| `POST /api/v3/devices/{device_id}/led/commands` | ID MQTT; corpo estrito `{desired_state: boolean}`; operador/admin proprietário; retorna envelope `command_status` |
| `WS /api/v3/events?device_id=...` | Envelopes v3 completos; ticket de `/api/v1/auth/ws-ticket` no primeiro frame |

REST exige Bearer e retorna `{success:true,data:...,meta:{schema_version:3}}`.
Resumo contém `environment`, `device` e `thresholds` consultados no PostgreSQL
(inclusive sem telemetria), além de `telemetry`, `prediction`, `prediction_unavailable_reason`,
`persistence`, `freshness`, `commands` e `alerts`. Antes da primeira leitura,
telemetria/previsão/persistência são nulas e freshness é `no_data`.
Extensão B2-27: o resumo inclui `inventory` mesmo com `telemetry=null`:
`{equipment_id: UUID, sensors: {ambient_temperature: UUID, humidity: UUID,
light: UUID, vibration: UUID, motor_current: UUID, motor_temperature: UUID},
actuators: {led: UUID, buzzer: UUID}}`. Os UUIDs são strings canônicas do
comissionamento, protegidas pela mesma sessão/propriedade do resumo; não incluem
credenciais, proprietário adicional nem coordenadas. Posições visuais são locais
ao frontend e vinculadas por esses IDs, sem inventar sensores pela telemetria.
`persistence` passa de `pending` a `persisted` após recibo vinculado. A projeção
durável PostgreSQL pode aparecer antes do ponto InfluxDB, sem depender da ordem
das filas. `commands` traz o último status de LED/buzzer ou nulo; `alerts`, até
100 últimos estados. Histórico contém telemetria, previsão original vinculada
ou nula e persistência. Não consulta nem transforma o bucket legado.

Extensão B2-14: histórico aceita `period=15m|1h|6h|24h` (padrão `1h`) ou par
`start/end` com fuso explícito, normalizado para UTC. O par explícito prevalece;
intervalo é `[start,end)`, filtrado no PostgreSQL antes de `LIMIT`. Metadados
incluem `device_id`, `start`, `end`, `count`, `limit` e limites atuais `thresholds`.
O frontend ordena os pontos cronologicamente; a classificação usa os limites
atuais, sem alegar que eram os limites vigentes no passado. Alertas aceitam o
mesmo par opcional e retornam intervalos que o intersectam, com abertura/fechamento
reais (`data.alerts`), sem inferir datas do último envelope. IDs de comando são
UUIDs; o caminho de solicitação LED continua usando a identidade MQTT.

Previsão antiga não é promovida para a leitura mais nova. Se uma previsão válida
envelhecer, resumo retorna `prediction=null` e motivo `stale_input`; histórico
conserva o envelope original. Timeout/freshness continuam com broker indisponível.
WS admite reentregas: deduplica últimos 1024 IDs em memória; cliente usa
`event_id` e REST na reconexão. Não há replay durável do stream.
O comissionamento atual usa um catálogo/equipamento e dono por runtime;
o PostgreSQL revalida propriedade, inclusive antes de cada envio WS.
Dependências antes da fonte ficam sem vínculo até sua chegada. Se a fonte
revelar divergência, são excluídas da projeção/entrega e auditadas como
`aiot_link_rejected`; o ACK antigo não é desfeito para encaminhá-las à DLQ.

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
consumidor. Inferência produz `stale_input` para entrada vencida; entrega B2-13
suprime previsão disponível envelhecida, informa `stale_input` no resumo REST
e emite freshness, preservando o evento histórico.
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

## Features e preparação de treino — B2-20

O cálculo comum em `backend/app/domain/features.py` serve aos adaptadores offline
e online. B2-20 prepara os dados; modelos e consumidor de inferência continuam
nas tarefas seguintes. Não há novo endpoint, envelope AMQP ou alteração live.

- Layout canônico por **janela → sensor → estatística**. Só sensores selecionados,
  na ordem de `SENSOR_TYPES`; nomes `{sensor}__{mean|std|trend|max}__{segundos}s`.
  Padrão: 900/3600 segundos, seis sensores, 48 colunas float64. Janelas são uma
  escolha inicial de engenharia, sem calibração nem ajuste pelo teste reservado.
- Intervalo **`[t-W,t)`**: inclui o limite inferior e exclui o instante atual,
  timestamps empatados com ele e qualquer futuro. Eixo offline: `observed_at`;
  online: `received_at` confiável do aceite, truncado para milissegundos UTC.
  `occurred_at` do dispositivo nunca define essa janela online. Históricos devem
  chegar ordenados; preparação offline agrupa/ordena máquinas antes do cálculo.
- Média, desvio **populacional (`ddof=0`)**, máximo e tendência OLS em unidade
  do sensor por hora. Cálculos locais usam tempos relativos e float64, sem somas
  cumulativas com épocas distantes. Overflow é erro explícito, não feature infinita.
- Menos de dois valores finitos em instantes distintos do sensor deixa suas
  quatro estatísticas NaN. Não há preenchimento com informação posterior.
  Histórico temporal suficiente exige início anterior/igual a `t-max(W)` e dois
  instantes distintos em cada janela; isso é separado dos faltantes por sensor.
  Online não imputa uma linha temporalmente insuficiente como previsão disponível.
- IDs, timestamps absolutos, modos, labels de degradação/saúde/RUL e censura
  nunca entram em X. Metadata/targets permanecem em arquivo separado.

O split ordena UUIDs, aplica permutação pela seed e distribui equipamentos em
70/15/15, com arredondamento e pelo menos um em cada conjunto. Exige **≥3
equipamentos**; nenhum ID cruza treino, validação e teste. Mesmos IDs + seed
reproduzem a divisão; uma nova geração tem novos UUIDs e é outro catálogo.

Depois da divisão, somente X do **treino** ajusta mediana e quantis 0,01/0,99 por
coluna. NaN recebe a mediana aprendida e valores extremos são limitados aos
quantis aprendidos; validação, teste e online apenas reaplicam esse estado.
Coluna sem nenhum valor útil no treino falha explicitamente. Não há escala extra.
`median-clip-v1` identifica essa política e seu estado JSON finito é imutável.
`features_version` combina `rolling-v1-<hash de layout/política>` e
`median-clip-v1`; o manifesto guarda nomes, janelas, sensores e estado aprendido.

Preparação `training-numpy-v1`: manifesto escrito por último, subdiretórios
`train`, `validation`, `test`, `features.npy` float64 e `targets.npy` estruturado.
Targets conservam `equipment_index`, `observed_at`, `health_score_true`,
`rul_hours_true` e `rul_observed`. Censurados participam de saúde; RUL deve usar
somente linhas com `rul_observed=true`, preservando zero como alvo válido.
É preparação interna em disco, sem registrar modelo/dataset novo no PostgreSQL.
Dados brutos, grupos, contagens e fonte privada são rastreados no manifesto.

O preparador reutiliza a validação B2-19 dos artefatos finalizados e imutáveis,
preservando o original. Mapeia NPY, processa equipamento a equipamento e escreve
blocos temporários de até 5.000 linhas; fit percorre colunas. Memória e tempo não
são constantes: dependem da quantidade de linhas, equipamentos e densidade nas
janelas. Falha deixa tentativa privada sem manifesto final; usar diretório novo
e limpar a tentativa incompleta manualmente. Não usar esses arquivos como treino
concluído nem misturá-los com telemetria live.

## Regressão offline de saúde — B2-21

`services/health_training.py:train_health` recebe uma preparação finalizada
`training-numpy-v1` e um destino novo separado da origem. Não aceita arquivos
pickle como entrada. Revalida layout/versionamento, transformação, contagens,
valores finitos, saúde 0–100 e grupos efetivos disjuntos entre partições. O formato
B2-20 conserva UUIDs por partição e índices nos targets, sem mapa índice→UUID;
a verificação prova disjunção dos dois conjuntos de identificadores, sem atestar
a correspondência individual. O chamador continua responsável pela origem privada
autorizada e por conservar os arquivos imutáveis durante a leitura.

Saúde é `100 × (1 − degradation_true)`, alvo latente exclusivamente offline.
Expoentes de desgaste, baselines dos sensores, modos e falhas variam por máquina
no gerador existente. Saúde inclui máquinas censuradas; não filtra `rul_observed`.

- `DummyRegressor(strategy='mean')` aprende só a média de saúde do treino.
- Dois `HistGradientBoostingRegressor` usam todo o treino, com 15/31 folhas,
  100 iterações, seed explícita, `early_stopping=False` e uma thread numérica.
  Os demais parâmetros efetivos são registrados no relatório.
- Menor **MAE na validação** escolhe o candidato; empate entre candidatos mantém
  o primeiro. Só é `eligible` se seu MAE for **estritamente menor** que o baseline
  na mesma validação. Empate ou pior resultado gera `rejected`.
- Escolha e elegibilidade são fixadas antes de abrir as matrizes de teste. Não há
  refit em validação/teste. Ambos são avaliados separadamente no teste reservado,
  inclusive quando o candidato é rejeitado; esse resultado não altera a decisão.
- Métricas usam previsões limitadas a 0–100: MAE, RMSE e R². R² vira `null`
  quando há menos de dois alvos, todos são constantes ou a variância numérica
  é zero; não se inventa R²=1.
  Faltantes já foram imputados com o estado do treino pela B2-20; NaN remanescente
  na matriz preparada é erro, sem ajuste de transformação nos reservados.

`health-training-v1` grava `report.json` por último, como marcador de conclusão.
Contém baseline/candidatos, parâmetros, escolha, métricas, seeds, versões,
features/transformação, fonte, partições, SHA-256 dos insumos, tempos e pico RSS
do processo inteiro. Tempo/memória variam; `ru_maxrss` inclui trabalho anterior
no mesmo processo, e não representa a soma da pilha. O fit usa o treino completo
em memória; o preparo em blocos não garante custo constante para o modelo.

Somente `eligible` grava `model.pkl`, bundle interno com estimador, especificação,
transformação, versão e faixa da previsão. O futuro consumidor deve reaplicar a
transformação e limitar a previsão à faixa registrada, usando versões compatíveis
e origem confiável. Pickle é restrito a artefatos internos: carregar um arquivo
externo pode executar código. Falha pode conservar pasta parcial sem relatório;
nunca tratar a presença de `model.pkl` isolado como treino concluído.

Essa etapa isolada não conclui job AMQP nem registra/ativa pacote em `models`: o contrato
existente exige saúde **e** RUL (duas unidades). A etapa offline RUL está descrita
na B2-22 abaixo; integração/registro de resultados na B2-23, ativação posterior.

## Regressão offline de vida útil restante — B2-22

`services/rul_training.py:train_rul` recebe o mesmo preparo B2-20, sem dividir
equipamentos novamente ou ajustar outra transformação. Produz estimador e
artefato independentes da saúde. Reutiliza validação/leitura/métricas da B2-21;
o helper de avaliação mantém o teto 100 por padrão para saúde e aceita `None`
para RUL, preservando previsões acima de 100 horas.

- Alvo **`rul_hours_true`**, unidade **horas**, com saída avaliada/apresentada
  limitada apenas em zero. Zero é válido quando a falha foi observada.
- `rul_observed=true` exige alvo finito e não negativo. `false` exige NaN no
  armazenamento, sem imputar zero. Censurados ficam fora do fit e das métricas
  RUL, mas todos os equipamentos continuam na verificação de disjunção.
- Treino, validação e teste precisam ter pelo menos um alvo observado. Ausência
  causa erro explícito, sem relatório final; não se inventa avaliação disponível.
- Dummy médio e dois HGB (15/31 folhas, 100 iterações, seed explícita, uma thread,
  sem early stopping) são ajustados apenas nos observados do treino. Escolha por
  menor MAE da validação e elegibilidade por melhora estrita sobre o baseline na
  mesma validação. Teste reservado aberto só após escolha/gate, sem refit.
- MAE/RMSE são em horas; R² segue a política numérica da saúde. Diagnóstico
  adicional em **`0 ≤ RUL ≤ 24 horas`**, incluindo zero e o limite 24, usa apenas
  observados da validação/teste. Faixa fixada antes do ensaio, sem escolher
  parâmetros por esse recorte. Recorte vazio registra `row_count=0` e métricas
  `null`, distinguindo ausência de evidência de erro zero.

`rul-training-v1` conserva `report.json` como marcador final e `model.pkl` apenas
se `eligible`. Relatório registra `target`, `unit`, `prediction_range=[0,null]`,
contagens totais/observadas/censuradas, métricas globais e `near_failure`, versões,
parâmetros, transformação, fonte, hashes, seeds, tempos e pico RSS. Bundle interno
também informa alvo/unidade/faixa; o consumidor futuro deve respeitá-los.
Aplicam-se as restrições de origem privada, imutabilidade, pickle confiável,
saída nova e tratamento de falha parcial da B2-21.

O benchmark B2-22 executa saúde e depois RUL em **processos separados e
sequenciais**, esperando cada filho encerrar antes de iniciar o outro. O pai usa
somente a biblioteca padrão e não mantém estimadores. Confere os sete arquivos
de entrada, igualdade do preparo/split/transformação e artefatos distintos;
`benchmark.json` só aparece após essas verificações. `rejected` conserva o
resultado diagnóstico sem afirmar que existem dois modelos aptos.

A filtragem de observados copia X; treino/validação são liberados antes de abrir
o teste. Isso reduz sobreposição, sem garantir RAM constante. RSS por processo
não deve ser somado como se os dois treinos estivessem simultâneos, nem tratado
como a capacidade da pilha completa.

Regressão apenas sobre falhas observadas pode ter **viés de seleção/censura**:
máquinas que não falharam não participam do ajuste. Prever para uma máquina
saudável não prova sua duração real; extrapolação além das histórias observadas
e transferência para hardware físico continuam sem validação. Não é modelo de
sobrevivência e não estima intervalo de confiança.
As funções offline isoladas não instalam executor AMQP nem registram/ativam;
a integração B2-23 abaixo registra o resultado sem alterar os schemas de jobs.

## Resultados e diagnósticos de treinamento — B2-23

O worker `training` reutiliza um preparo B2-20 e executa saúde/RUL em filhos
sequenciais, com seed fixa 42. Checkpoints no pai verificam a conexão do lock
durante o cálculo a cada dois segundos; falha encerra o filho. Retomada refaz
o cálculo em nova pasta, sem diminuir `completed_units`. Duas etapas concluídas
ainda podem preceder a validação/registro final do pacote.

`training-package-v1` reúne manifesto preparado, relatórios e hashes. O registro
privado em `models` satisfaz a FK do resultado de um job concluído; **não altera
`active_models`/`model_activations`**. Um cálculo com candidato `rejected` pode
concluir e exibir seus erros, sem publicar o pickle desse candidato. O pacote só
é apto se ambos superarem estritamente o MAE de validação dos seus baselines.
Falha de cálculo/artefato é `TRAINING_FAILED`, sem resultado concluído.

| Rota | Regra / resposta |
| --- | --- |
| `GET /api/v3/datasets` | Sessão atual; até 50 datasets próprios de geração concluída, mais recentes primeiro: `id,name,row_count,created_at,generation_job_id`. Lista vazia é válida. |
| `GET /api/v3/jobs/{job_id}/result` | Sessão/dono conferidos antes de ler disco. Somente job de treino concluído e pacote vinculado ao mesmo job/dataset. `404 JOB_NOT_FOUND` alheio/ausente; `409 TRAINING_NOT_READY` não concluído; `503 TRAINING_RESULT_UNAVAILABLE` para resultado inseguro/inválido. |

Sucesso usa `{success:true,data:...,meta:{schema_version:3}}` e `no-store`.
Resultado contém IDs, `model_version`, `eligible`, `features_version`, `seed`,
`split_seed`, contagem de equipamentos por partição, versões, `health`, `rul` e
limitações. Cada alvo contém `target`, `unit`, `status`, métricas
`validation|test.baseline|candidate.{mae,rmse,r2}`, linhas por partição,
`diagnostics` e `near_failure` (somente RUL, recorte B2-22).

`diagnostics` usa **somente teste reservado depois da escolha**, com até 500
linhas, sem reposição, seed do treino e índices ordenados. `scatter` informa
`actual,predicted,baseline,error`, com erro = previsto − real. Importância é o
aumento de MAE ao permutar cada feature, três repetições na mesma amostra, uma
thread e o mesmo clipping da avaliação: média/desvio padrão, referência MAE,
nomes, quantidade e método registrados. Valores negativos são preservados;
correlação pode diluir importância e não há interpretação causal. Métricas
globais continuam nas partições completas; a amostra não escolhe modelo.

A leitura HTTP aceita JSON limitado, finito e validado, confere identidades,
alvo/unidade/faixa, split/transformação, gate, contagens e hashes de
relatórios/modelos. Nunca desserializa pickle nem entrega caminhos, matrizes ou
parâmetros privados. Arquivos ficam na raiz separada `TRAINING_ARTIFACT_ROOT`
(RW no treino/RO na API); a fonte de datasets continua RO para ambos.

Frontend `/training` segue o acesso administrativo do Laboratório; recupera
`?job=UUID`, consulta progresso sem repetir POST e oferece tabelas para gráficos.
Os GETs continuam privados por dono para qualquer papel autenticado no backend;
o POST permanece exclusivamente administrativo. Dados sintéticos e censura de
RUL impedem interpretar aptidão offline como precisão física comprovada.

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
valida propriedade PostgreSQL. Status/timeout durável e autorização HTTP v3 são
implementados na B2-13; cache do simulador segue em memória.

## Jobs HTTP e progresso SSE — B2-17

Rotas instaladas quando `RABBITMQ_API_PASSWORD` está configurada. Bearer obrigatório;
proprietário vem da sessão e é conferido no PostgreSQL. Papel admin não permite
ler registros alheios. Respostas privadas usam `Cache-Control: no-store`.

| Rota | Regra |
| --- | --- |
| `POST /api/v3/jobs` | Somente admin atual; retorna `202` após transação job + outbox, sem executar cálculo nem esperar broker |
| `GET /api/v3/jobs/{job_id}` | Qualquer papel lê somente o próprio job; inexistente/alheio retorna `404 JOB_NOT_FOUND` |
| `GET /api/v3/jobs/{job_id}/events` | SSE privado com Bearer no header, revalidação de sessão e dono a cada segundo; fecha em estado terminal/revogação/perda de propriedade |

Geração recebe `{"job_type":"generation","total_units":1000000,"seed":42}`;
`total_units` inteiro estrito entre 1 e 2 milhões; seed inteiro estrito entre 0 e
`2**32-1`, padrão 42. Treino recebe `{"job_type":"training","dataset_id":"UUID"}`;
dataset deve pertencer à conta, ter chave interna de artefato e de 1 a 2 milhões
de linhas registradas. Seu total é fixo em duas regressões. Ambos aceitam
`environment_id` UUID opcional da própria conta. Campos extras são recusados;
o cliente não envia dono, caminho, status nem resultado. B2-23 conecta a validação
aprofundada do preparo/modelos antes de registrar o resultado concluído.

Parâmetros opcionais da geração B2-18 (configuração persistida no job e manifesto):

| Campo | Padrão | Validação / efeito |
| --- | --- | --- |
| `equipment_count` | 100 | Inteiro estrito 1–10.000; linhas distribuídas entre equipamentos sintéticos |
| `days` | 30 | Número finito >0 e ≤3650; janela máxima simulada por equipamento |
| `sensor_types` | Seis nomes de medições offline abaixo | Lista não vazia, sem repetição; tipos ausentes tornam-se null na linha lógica |
| `failure_fraction` | 0.6 | Número finito 0–1; probabilidade de falha observada por equipamento |
| `failure_modes` | `["bearing_wear","imbalance"]` | Subconjunto não vazio, sem repetição |
| `operating_modes` | `["normal","heavy","cycling"]` | Subconjunto não vazio, sem repetição |
| `noise_scale` | 1 | Número finito 0–10; multiplicador do ruído gaussiano |
| `missing_rate` | 0.01 | Número finito 0–1; probabilidade por medição selecionada |
| `outlier_rate` | 0.002 | Número finito 0–1; probabilidade de perturbação extrema por medição |

Números não aceitam strings/booleanos. `total_units` conta observações de
equipamento com até seis medições; quantidade de sensores = equipment_count ×
quantidade de tipos selecionados. Não é contagem de células nem de eventos live.
Armazenamento físico e operação em [backend](../backend/README.md#geração-offline-b2-18).

Resposta HTTP: `{success:true,data:{id,owner_user_id,config,job_type,status,completed_units,total_units,
result_id,error_code,environment_id,dataset_id,created_at,updated_at},meta:{schema_version:3}}`.
Na B2-19, `owner_user_id` identifica o autor autenticado e `config` recupera a
configuração persistida, inclusive campos guardados em colunas separadas. Para
geração, contém o `GenerationInput` completo; esses campos não alteram o envelope AMQP.
`result_id` é nulo até conclusão com artefato registrado do próprio job e arquivo
interno regular, não vazio e sem symlink. Geração e treino têm executores offline;
ausência de executor real falha explicitamente, com o código correspondente.

SSE emite `event: job_progress` com essa **resposta HTTP** no campo `data`, quando
`updated_at` muda; não é o envelope AMQP abaixo. É uma assinatura do estado durável,
consultada a cada segundo; pode coalescer checkpoints rápidos. Comentário keep-alive
a cada 15 s conserva o proxy. Após queda, GET/reconexão recupera o estado atual;
não há replay integral de eventos. Erro durante stream emite `event: error` com
`DEPENDENCY_UNAVAILABLE` sanitizado e fecha; falha inicial de banco retorna 503.
Para browser usar `fetch` com header Bearer; `EventSource` nativo não recebe esse
header. Tokens em URL não autenticam a rota.

Solicitações e progresso continuam publicados no AMQP com outbox própria.
O consumidor WebSocket de dispositivos não é usado para jobs sem dispositivo.
Um lock PostgreSQL de sessão, comum a todos os donos/tipos, serializa executores;
contenção/indisponibilidade de banco conserva entrega pendente sem gastar retries
do broker. Checkpoint só pode avançar e é persistido com evento na mesma transação.
Executores devem gravar blocos duráveis antes do checkpoint e interromper ao
perder a conexão. O lock não garante exclusão durante perda da sessão PostgreSQL
entre checkpoints de um executor ainda vivo; B2-23 encerra seus filhos ao detectar
a falha no próximo checkpoint (até dois segundos durante cálculo). Esse intervalo
não é fencing distribuído; não foi implementada alta disponibilidade.

## Consulta privada de datasets — B2-19

Instalada junto das rotas de jobs. Bearer no header e dono obtido da sessão;
até admin recebe `404 DATASET_NOT_FOUND` para dataset alheio. Somente resultado
do job de geração concluído e vinculado pode ser lido. Respostas têm
`Cache-Control: no-store`; caminhos internos nunca são publicados.

- `GET /api/v3/datasets/{id}` devolve `{success:true,data:{id,owner_user_id,
  generation_job_id,created_at,row_count,config,storage_version,units,quality},
  meta:{schema_version:3}}`. `config` é a configuração completa de geração.
- `quality.missing_by_sensor` conta valores faltantes somente dos sensores
  selecionados. `range_by_sensor` informa `{min,max}` observados por sensor;
  ambos são null quando todos os valores faltam. `rul_observed_rows` e
  `rul_censored_rows` contam **linhas**, cuja soma é `row_count`.
- `GET /api/v3/datasets/{id}/sample` é uma consulta separada. Devolve no mesmo
  envelope `data:{dataset_id,rows:[{equipment_id,observed_at,measurements,
  degradation_true,health_score_true,rul_hours_true,rul_observed}]}` com as dez
  primeiras linhas. NaN vira null. A amostra determinística não representa a
  distribuição inteira; labels continuam exclusivamente offline.

O leitor percorre NPY com memória limitada por bloco, conferindo manifesto,
contagem, dtype, tamanho, hashes e caminhos internos sem symlink. Artefato ausente,
incompatível ou corrompido retorna `503 DATASET_UNAVAILABLE`, sem detalhes de disco.
Resumo lê todos os blocos a cada consulta, separado do polling de progresso;
há custo de I/O proporcional ao dataset. Não há importação, download completo,
treino nem escrita em telemetria live. Outliers são uma taxa **configurada**,
sem contagem observada: a máscara das perturbações não está armazenada.

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

### Ativação implementada — B2-24

| Rota | Regra / resposta |
| --- | --- |
| `GET /api/v3/models` | Sessão atual; até 50 pacotes próprios de treino concluído: IDs, versões, métricas e data. Inclui rejeitados para inspeção; não expõe caminhos. |
| `GET /api/v3/models/active` | Versão ativa persistida da conta (`model_id`, versões, `activated_at`), ou `data:null`. |
| `POST /api/v3/model-activations` | Admin atual; corpo estrito `{model_id: UUID}`. Retorna `202` com ativação `ready`, ID, versões, anterior, datas e erro. |
| `GET /api/v3/model-activations/{id}` | Status privado recuperável por ID, inclusive `failed/MODEL_LOAD_FAILED`. |

Respostas seguem envelope v3 e `no-store`. Sem credencial AMQP da API, essas
rotas não são instaladas. `404 MODEL_NOT_FOUND` cobre pacote ausente/alheio ou
sem resultado de treino concluído; `409 MODEL_NOT_ELIGIBLE` rejeita candidato
não aprovado; `409 ACTIVATION_PENDING` impede novo pedido enquanto há carga.
Consulta alheia/ausente usa `404 MODEL_ACTIVATION_NOT_FOUND`. Falha de JSON/hashes
no POST usa `503 TRAINING_RESULT_UNAVAILABLE`; erro PostgreSQL usa `503` sanitizado.

O pedido e `model_activation` são persistidos juntos em `model_outbox` pela API.
Worker `models` usa a identidade `inference`, consome a fila dedicada
`coldsafe.model-activation` e confere o evento contra a solicitação persistida.
O lock de sessão por proprietário atravessa o checkpoint `loading`. Depois de
validar e carregar **ambos** os estimadores, a mesma transação troca
`active_models`, conclui a ativação e grava `model_status`. Falha conserva o
ponteiro/bundle anterior; duplicata terminal não repete a troca. Interrupção em
`loading` permite repetir a carga pelo mesmo ID em outro processo.

O carregador reutiliza `training-package-v1`: fonte, layout, unidades, transformação,
baseline/gate e SHA-256 são revalidados antes do pickle. Exige Python major/minor
igual e versões numéricas registradas exatamente iguais; confere tipos, parâmetros,
layout e uma previsão finita após carregar. Aceita apenas referências internas
registradas de jobs concluídos, nunca uploads/URLs/caminhos no HTTP. Hash detecta
corrupção, não autentica um produtor malicioso: worker/volume continuam confiáveis.

Correção de compatibilidade: apenas `features_version` também aceita `+`, usado
desde B2-20 em `rolling-v1-<hash>+median-clip-v1`. Identificadores já produzidos
são preservados; `model_version` mantém a regra anterior. Reconstruir consumidores
com o schema atualizado antes de publicar esses eventos.

Recuperação da versão anterior usa novo POST com o `previous_model_id` de uma
ativação; revalida o pacote e serializa a troca novamente, sem alterar registros
manualmente. Preserve os artefatos das versões anteriores. Publicação com confirms
e outbox pode duplicar transporte, mas conserva `event_id`. Perdas repetidas podem
esgotar o limite do broker e exigir redelivery manual da solicitação original na
DLQ; não apague uma ativação pendente para contornar a exclusão.

Essa etapa não processa telemetria nem reidrata o cache do consumidor de previsões
ao reiniciar: isso pertence à B2-25. O registro ativo sobrevive ao restart. A cópia
de `model_activation` na fila `inference` continua preservada para essa integração;
o novo worker não consome essa fila nem descarta sua telemetria.

### Inferência ao vivo implementada — B2-25

O overlay `compose.inference.yaml`, aplicado depois de AIoT/jobs, troca o comando
do serviço `models` para `backend.app.inference_worker`: ativação e previsão usam
um processo, uma identidade AMQP `inference` e a mesma instância de `ModelService`.
Consome a fila própria `coldsafe.inference` (telemetria e cópia de ativação) e a
fila dedicada da B2-24; replay de ativação terminal não reverte a versão atual.
Catálogo, IDs de sensores/atuadores, propriedades AMQP e proprietário atual são
validados. O escopo comissionado continua sendo um equipamento/dono por runtime.

`sync_active` restaura o pacote autorizado ao iniciar e confere o ponteiro antes
de cada entrada. Só recarrega quando o ID muda; ativação bem-sucedida substitui
os dois estimadores juntos. Falha da ativação mantém anterior; falha ao restaurar
um ativo em outro processo produz `model_unavailable`, sem rotular o bundle antigo
com a nova versão. Banco indisponível/lock ocupado preservam a entrega para retry.

A migração **010** acrescenta `inference_events`: fonte, previsão canônica e
marcação de publicação. O processamento revalida propriedade no PostgreSQL,
serializa por dono/dispositivo e grava fonte+previsão numa transação antes do ACK.
UUID da previsão deriva da fonte; redelivery retorna o envelope já persistido,
mesmo após troca de modelo. UUID reutilizado com outro conteúdo não é aceito.
Outbox publica com confirmação antes de marcar; falha pode duplicar transporte,
mas não recalcula nem cria outra identidade. Publicação também revalida dono ativo.

Histórico usa exclusivamente `received_at` aceito, truncado em milissegundos,
ordenado por horário/ID, e o mesmo `telemetry_features`/transformação do treino.
Cada janela é `[cutoff-duration, cutoff)`: a própria entrada, leituras futuras e
amostras no mesmo milissegundo ficam fora de X. SQL busca a maior janela passada
e uma âncora anterior para provar extensão temporal. Limite explícito de **10.000
registros, incluindo âncora**; excesso gera `invalid_features`, sem amostragem.
Padrão permanece 900/3600 segundos: sem histórico persistido anterior, o warm-up
exige uma hora e ao menos duas observações em tempos distintos por janela.
Entradas sem modelo também compõem histórico para uma ativação posterior.

Inferência calcula saúde e RUL com uma thread e limita saúde a 0–100/RUL a zero
no mínimo. Valores devem ser finitos e sair juntos. Falta de modelo tem prioridade
`no_model`; com modelo, histórico curto é `insufficient_history`, falha de features
é `invalid_features`, falha de carga/execução é `model_unavailable` e entrada
com idade maior que 30 s é `stale_input`. Idade é reavaliada após o cálculo.
Zero RUL continua válido. Não há labels, nova interpretação de censura ou alteração
de thresholds/alertas; Insights/histerese preditiva são B2-26.

O dashboard AIoT mostra saúde, RUL em horas, versões e horários da previsão e da
entrada, ou o motivo textual de ausência. Prediction WS invalida REST; o resumo
autorizado continua a fonte da interface. Parser verifica vínculo completo com
a leitura atual, sem substituir uma leitura nova por previsão antiga. Freshness
local oculta números vencidos sem renovar a idade da telemetria.

Histórico/outbox não têm expurgo automático; consulta por janela limita memória,
não crescimento do disco ou custo de I/O. Não apagar linhas referenciadas/pendentes
para refazer o warm-up: isso quebra deduplicação/identidade. Catálogo/proprietário
revogado encerra esse worker de forma fechada, sem liberar saídas; o restart herdado
requer recomissionar a configuração. Limites medidos da pilha inteira continuam B2-33.

### Alertas preditivos e Insights — B2-26

`GET /api/v3/insights?device_id=<mqtt_device_id>` exige sessão e propriedade
atual do dispositivo comissionado. Responde no envelope HTTP v3 com
`device_id`, `equipment_id`, `rules`, `prediction` (envelope v3 ou `null`),
`availability` (`available`, `unavailable`, `stale`, `no_data`), `age_seconds`,
`trend` (`improving`, `declining`, `stable`, `unknown`) e `active_alerts`.
Cada alerta contém `alert_id`, `kind=predictive_failure`, `opened_at`,
`source_event_id` e `prediction_event_id`. Conta/dispositivo fora do escopo
retorna 404, sem expor dados. A página consulta o estado persistido por HTTP.

`PUT /api/v3/insights/rules?device_id=<mqtt_device_id>` exige operador/admin e
propriedade atual. Recebe exatamente os seis campos abaixo e retorna as regras
diretamente em `data`; não aceita campos extras, strings numéricas, booleanos,
valores não finitos ou contagens fracionárias. Regras pertencem ao proprietário.

| Campo | Inicial | Validação |
| --- | --- | --- |
| `health_critical` | 30 | 0 ≤ crítico < recuperação ≤ 100 |
| `health_recovery` | 40 | Mesmo intervalo acima |
| `rul_critical_hours` | 24 | 0 ≤ crítico < recuperação, finitos |
| `rul_recovery_hours` | 48 | Mesmo intervalo acima |
| `open_count` | 3 | Inteiro entre 1 e 100 |
| `close_count` | 10 | Inteiro entre 1 e 100 |

Saúde ≤ crítico **ou** RUL ≤ crítico conta criticidade; saúde ≥ recuperação
**e** RUL ≥ recuperação conta recuperação. A faixa entre esses valores zera
a sequência e conserva o alerta aberto. Ausência/indisponibilidade e entrada
com mais de 30 s não encerram alertas. Previsão precisa de fonte e recibo
vinculados e autorizados. Fonte com instante igual/anterior ao último avaliado
não avança o estado; uma previsão ainda recente pode ser avaliada mesmo se a
telemetria seguinte já chegou, para tolerar atraso entre filas. A tela continua
vinculada à última telemetria.

A migração 011 guarda regras, sequência por dono/dispositivo/equipamento e
histórico de alertas. Abertura/encerramento e auditoria compartilham a transação
do consumo antes do ACK; índice único impede dois alertas abertos no escopo.
Reinício preserva estado e recarga recupera os alertas. Alterar regras audita e
zera sequências, sem encerrar alertas. Troca de modelo também reinicia a sequência
e a comparação de tendência, preservando o alerta aberto. Não cria comando nem
altera buzzer térmico.

Tendência compara as duas últimas previsões elegíveis: qualquer queda em saúde
ou RUL é `declining`; sem queda, qualquer subida é `improving`; iguais são
`stable`; sem comparação é `unknown`. Não é prognóstico adicional do modelo.
Limiares iniciais são configuráveis de protótipo, sem calibração física.
Histórico/auditoria permanecem sem expurgo automático.

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
Na B2-18, `degradation_true` opcional 0–1 registra o desgaste sintético por linha;
o novo gerador sempre o grava. É opcional no schema para preservar linhas antigas.

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

## Estado do modelo local — B2-30

`GET /api/v3/llm/status` exige Bearer de sessão válida (401 sem sessão ou após
revogação); não exige papel administrativo. Resposta `200`, `Cache-Control:
no-store`, sem dados de contas/jobs:

```json
{"success":true,"data":{"state":"ready","model":"llama3.2:3b-instruct-q4_K_M"},"meta":{"schema_version":3}}
```

| `state` | Significado |
| --- | --- |
| `disabled` | `OLLAMA_URL` não configurada |
| `loading` | Pré-carga em curso ou necessária |
| `ready` | Modelo residente em CPU/contexto 1.024 confirmado |
| `paused` | Cálculo pesado reserva a memória; inclui job `running` sem lock vivo |
| `model_missing` | Pesos locais ainda não preparados |
| `unavailable` | Estado não confirmado no Ollama/PostgreSQL ou pré-carga ambígua exige recuperação operacional |

A consulta não carrega/baixa modelos e não aceita prompt, modelo ou URL do
cliente. O estado é global da infraestrutura; não identifica o job nem seu dono.
O resumo privado e streaming estão implementados na B2-31 abaixo; a página
Assistente e sua avaliação de respostas pertencem à B2-32.

## Assistente HTTP e streaming — B2-31

`POST /api/v3/llm/ask`, Bearer de sessão válida, permite todos os papéis.
Corpo fechado: `{"question":"Qual a saúde e RUL do equipamento?"}`. Pergunta
não vazia, até **256 bytes UTF-8** (inclusive espaços antes de normalizar);
campos como proprietário, contexto, histórico, modelo e ferramentas são recusados.
Não existe memória de conversa: cada pergunta recebe um novo resumo privado.

O backend consulta somente fatos do proprietário autenticado em transação
`READ ONLY`: contagens de leituras ausentes/antigas, menores saúde e RUL entre
previsões atuais, seis sensores do primeiro equipamento selecionado, contagens
de alertas, MAE de teste de saúde/RUL do modelo ativo e arquitetura curta.
IDs e versões são limitados; nomes livres, caminhos, credenciais e IDs de donos
não entram no resumo. A seleção é amostra, não histórico completo; omissão é
explícita. Após 30 s, números antigos não são apresentados como atuais.

Sucesso: `200 text/event-stream`, `Cache-Control: no-store` e
`X-Accel-Buffering: no`. Cada evento contém uma linha JSON, sem HTML interpretado:

```text
event: delta
data: {"text":"A saúde informada é "}

event: delta
data: {"text":"20."}

event: done
data: {"request_id":"<uuid>"}

```

`done` confirma término e auditoria, sem certificar exatidão da linguagem natural.
Após iniciar o SSE, falha termina com `event: error` e `data: {"code":"..."}`,
sem `done`: `LLM_TIMEOUT`, `LLM_UNAVAILABLE` ou `UNAUTHORIZED`. O cliente deve
tratar texto parcial e saída como não confiáveis; nunca executar HTML, links,
imagens remotas ou instruções produzidas pelo modelo.

Antes do SSE, erros seguem o envelope HTTP existente: 401 sem sessão; 422 para
entrada inválida; 429 `RATE_LIMITED`, com `Retry-After: 60`; 503 `LLM_DISABLED`,
`LLM_BUSY`, `LLM_NOT_READY` ou `LLM_UNAVAILABLE`. Há **cinco admissões por conta
em janela móvel de 60 s**, compartilhadas entre processos/reinícios; tentativas
admitidas que terminam indisponíveis também contam. Pedidos inválidos não contam.
Uma geração global por vez, sem fila de espera, usando o lock dos jobs.

Geração tem prazo de 90 s no perfil 3B da B2-32; HTTP tem conexão de 3 s e leitura
de até 90 s, limitada pelo mesmo prazo total; consultas
novas deste percurso têm limite de 3 s, e limpeza/descarga até 12 s. O prazo de
90 s não inclui pré-validação nem limpeza. Saída: até 256 tokens gerados, 8 KiB
por linha do protocolo, 64 KiB recebidos e 16 KiB de texto. Contexto 1.024 tokens:
a tokenização varia; esses limites não garantem resposta integral para toda
pergunta Unicode. O ensaio B2-31 mediu 289–429 tokens de entrada nos três casos.
O proxy usa inatividade de até 120 s para permitir a geração de 90 s e a limpeza
antes do terminal SSE; isso não amplia o prazo de geração do backend.
O navegador limita a chamada completa a 130 s, incluindo rede e pré-validação,
para não abortar uma geração válida durante a limpeza do servidor.

Desconexão fecha o HTTP e confirma descarga antes de liberar o slot. Sessão é
revalidada por parte e antes de `done`. Falha ambígua de descarga ou perda da
sessão PostgreSQL mantém `llm_memory_guard`: exige a recuperação segura descrita
na B2-30, sem apagar o marcador enquanto Ollama puder continuar calculando.

Auditoria local em `audit_events`: `assistant.requested` guarda autor, UUID,
pergunta e modelo; `assistant.finished`, resultado; `assistant.limited`, hash da
pergunta recusada. Não guarda token, resumo ou resposta. Auditoria inicial é
obrigatória antes do modelo; auditoria terminal e retirada do marcador são
atômicas. Falha de conexão pode deixar somente o pedido, com log de falha de
auditoria e marcador conservado. Sem expurgo automático; não incluir segredos
nas perguntas. Ollama só recebe resumo/pergunta, sem banco ou ferramentas.

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
