# Apresentação final — 16/11/2026

Apresentação presencial em 2026-11-16, diretamente na aplicação, sem slides.
**Roteiro revisado na B2-35 em 23/10/2026; B2-36 concluída por aceite manual do usuário em 25/10/2026.**
A ordem abaixo reproduz o [enunciado do professor](../history/assignment.md).
Resultados anteriores são identificados como evidência histórica; este documento
não afirma que os 12 passos tenham sido executados novamente. A preparação
Docker de 02/11/2026 está registrada separadamente abaixo.

## Preparação Docker do redesign — 02–03/11/2026

**Redesign e núcleo operacionais; apresentação completa pendente do assistente.**
O redesign foi reconstruído com AIoT habilitado,
usando os cinco arquivos Compose do runbook e os volumes pessoais existentes.
A entrada continua em [http://localhost:5173/](http://localhost:5173/), com Nginx
sem root e API/Swagger locais. Não houve commit, push, troca de senha ou papel,
nem descarte de volumes, filas, datasets ou modelos.

- O intervalo privado `SIMULATOR_INTERVAL_SECONDS` passou de `1` para `5`.
  `SIMULATOR_STEP_SECONDS=60` foi preservado: cada leitura avança um minuto de
  desgaste sintético, agora a cada cinco segundos de relógio. Isso equivale a
  12× no desgaste, não acelera as janelas UTC das features. Recriar o simulador
  reiniciou seu estado físico em memória; isso não demonstra recuperação de falha.
- O gateway ganhou índices de pendentes em `ingress(sent)` e `errors(sent)`.
  Eles são criados também em diários existentes, preservando registros, ordem
  e deduplicação. O plano deixou de varrer todos os enviados para procurar
  pendências. O ganho total de latência não foi isolado das demais intervenções.
- A API passou a capturar `AMQPConnectorStackTimeout` no laço de reconexão já
  existente. Essa exceção do Pika não herda de `AMQPError`: antes encerrava uma
  thread, deixando consultas HTTP disponíveis, readiness em `503` e a fila de
  comandos sem consumo. Testes verificaram duas falhas, backoff e reconexão.
- A primeira rodada encontrou duas recusas `LLM_BUSY` e uma geração expirada
  sem resposta. Houve degradação e reinícios por timeout de handshake AMQP;
  não foram observados eventos Docker `oom` nessa coleta. A rodada começou
  na bateria; depois o usuário conectou o carregador. Esses fatos não provam
  uma causa única. Docker Desktop foi reiniciado sem remover volumes.
- O marcador `llm_memory_guard` deixado por uma carga interrompida foi recuperado
  pelo procedimento do runbook: coordenador parado, Ollama reiniciado, nenhum
  job em execução, remoção somente do marcador operacional e retomada.
- Após a recuperação, telemetria atual/persistida voltou à API. Dois comandos
  de LED foram comprovados por estado `pending`, ACK `confirmed` e telemetria
  observada: ligar e depois desligar, restaurando o estado inicial. Um comando
  anterior durante o backlog terminou `unconfirmed`, sem ser contado como sucesso.
- O 3B expirou também na tomada e em ensaio temporário de 4 GiB, sem primeira
  parte de resposta. O teto original de `3328m` foi restaurado. Houve paginação
  intensa do host; aumentar o limite do container não resolveu o ensaio.
- Em 03/11, o usuário autorizou o candidato `llama3.2:1b-instruct-q4_K_M`,
  mantendo seus aplicativos abertos e os modelos de saúde/RUL. Os pesos 1B foram
  baixados sem apagar os 3B. O 1B foi **reprovado por qualidade factual** nos
  testes com PostgreSQL/Ollama CPU reais e fixtures declaradas: inventou RUL de
  5 h em vez de 10 h e inventou saúde/RUL atuais para leituras antigas. A troca
  de perfil foi revertida; não apresentar o 1B como aprovado ou como solução.
  [Respostas e fatos](../evidence/docker-presentation-2026-11-02/quality-1b-2026-11-03.json)
  e [revisão independente](../evidence/docker-presentation-2026-11-02/quality-1b-independent-review-2026-11-03.json).
- Também por autorização do usuário, o Qwen `qwen2.5:1.5b-instruct-q4_K_M`
  foi testado isoladamente em 03/11, com PostgreSQL e Ollama CPU reais e os
  mesmos 14 casos do avaliador existente. Na primeira rodada, duas respostas
  concluíram, uma geração ficou sem conclusão SSE e onze encontraram o modelo indisponível após a
  descarga. Uma única revisão mais curta das instruções, mantendo resposta em
  português e os limites de segurança, foi avaliada em outro banco descartável:
  cinco respostas concluíram, uma geração ficou sem conclusão SSE e oito registraram
  `LLM_NOT_READY`. O Qwen chamou a previsão de RUL de 10 h de “limitação de
  10 horas” e omitiu a limitação pedida na pergunta sobre métricas. A revisão
  independente o **reprovou por qualidade e disponibilidade**. Os casos sem
  resposta não comprovam alucinação nem qualidade factual; em particular,
  ausência de dados, leituras antigas e holdouts não puderam ser avaliados.
  [Rodada inicial](../evidence/docker-presentation-2026-11-02/quality-qwen-initial-2026-11-03.json),
  [rodada adicional](../evidence/docker-presentation-2026-11-02/quality-qwen-short-prompt-2026-11-03.json)
  e [revisão independente](../evidence/docker-presentation-2026-11-02/quality-qwen-independent-review-2026-11-03.json).
- As sete substituições de identificador e os dois arquivos do experimento de
  instruções/teste foram restaurados byte a byte. O candidato não foi liberado
  na conta pessoal. Os dois bancos descartáveis foram removidos após preservar
  os relatórios, sem criar comandos de atuadores. As imagens de backend,
  geração, treino, modelos e coordenador foram reconstruídas com o perfil 3B
  original; os quatro primeiros serviços foram retomados e verificados.
- A resposta completa e factualmente adequada do assistente continua pendente.
  `healthy`, velocidade ou ausência de comandos indevidos não atendem sozinhos
  a esse critério. Outro perfil depende da escolha do usuário e de nova avaliação.
  Ao encerrar o teste Qwen, os 12 serviços principais estavam saudáveis, readiness
  e resumo retornavam `200`, e a telemetria estava atual/persistida. Ollama e seu
  coordenador ficaram parados; o backend voltou ao identificador 3B. Não prometer
  novos jobs pesados nessa condição: a coordenação configurada exige confirmar
  a descarga do Ollama antes de iniciar geração/treino. A pilha completa deve
  ser retomada e ensaiada após qualificar o próximo perfil.
  A conferência autenticada final encontrou seis medições atuais/persistidas,
  previsão disponível, LED desligado e a mesma versão preditiva anterior.
  Permanecem duas contas (admin e operador), um dataset, dois jobs concluídos e
  um modelo ativo; não foram gerados ou treinados novos artefatos pessoais.

Verificação nova: build Docker com typecheck, 31 funções de teste existentes de
configuração executadas diretamente com asserts (sem fixtures), e 40 testes do
gateway em Python 3.13.15; cobertura do módulo `gateway.bridge`, incluindo ramos,
de 95,24%; outros 40 testes do consumidor AMQP passaram, com 89,77% no módulo.
No candidato 1B passaram 72 testes de protocolo/backend e 12 do componente de
estado, mas isso não aprovou a linguagem. Após restaurar o identificador 3B,
90 verificações de protocolo/coordenação passaram em Python 3.13.15 no cliente
Linux descartável: PostgreSQL real, executores pequenos e Ollama simulado nessa
suíte, com 97,09% no módulo `backend.app.services.llm`, incluindo ramos.
No candidato Qwen, os 90 testes de protocolo/coordenação e 12 testes do estado
no frontend também passaram. A última suíte do candidato cobriu `llm` e
`assistant_transport`, com 96,49% combinados, incluindo ramos. Isso é teste de
protocolo com Ollama simulado e PostgreSQL real, separado das duas avaliações
de texto com Ollama real; não constitui aprovação factual do Qwen.
O ambiente do cliente foi isolado das opções de produção; as fixtures criaram
e removeram bancos próprios. Esses testes não comprovam respostas do modelo.
O pytest do ambiente pessoal ficou bloqueado em leitura de arquivos;
os testes do gateway usaram ambiente temporário com versões já fixadas. Não é
uma nova execução da suíte completa nem cobertura global. Nenhuma dependência
Python/Node foi adicionada ao projeto. Os pesos experimentais 1B (cerca de
808 MB) e Qwen (cerca de 986 MB) são artefatos novos de infraestrutura,
preservados no volume e sem aprovação de uso. Os pesos 3B foram preservados.

Próxima ação recomendada, ainda não implementada: avaliar execução acelerada
do perfil 3B, antes de escolher outro modelo pequeno. A documentação atual do
[Docker Model Runner](https://docs.docker.com/ai/model-runner/inference-engines/)
descreve aceleração Metal para Apple Silicon. Isso é uma alternativa técnica,
não uma medição neste Mac: exige conferir disponibilidade local, adaptar os
contratos de inferência/carga/descarga e repetir os testes de memória, segurança
e qualidade. Depende de nova escolha do usuário; não foi instalado nem ativado.

Planejamento posterior, em 03/11: o usuário escolheu documentar um
[roadmap do assistente com Metal](assistant-metal-roadmap.md), com ensaio futuro
na bateria e aplicativos pessoais abertos. O documento separa viabilidade
isolada de integração com a pilha, define critérios e reversão e registra as
consultas de disponibilidade já realizadas. Somente a documentação foi
autorizada nesta entrega; implementação, download e execução continuam pendentes.
Esse cenário não altera a condição na tomada do roteiro de apresentação abaixo.

O navegador autenticado confirmou seis medições, histórico e modelo ativo;
WebGL 2 real com nove componentes, seleção por teclado, ID/dados associados e
reflow em 390 px. A captura em
[390 px](../evidence/docker-presentation-2026-11-02/twin-390px.jpg) é da primeira
rodada, antes da recuperação operacional; não comprova a condição final da pilha.
O dataset de um milhão e os dois jobs concluídos são de 25/10/2026, preservados
e consultados novamente, não geração/treino novos.

No fechamento complementar da RD-18 em 03/11, as quatro telas autoatualizadas
receberam controle de ocultar/mostrar dados ao vivo, mantendo coleta e comandos.
O ensaio atual com leitor de tela foi dispensado pelo usuário e continua sem
validação demonstrada. Consulte o [checkpoint RD-18](../redesign/tasks/RD-18.md#checkpoint).
Esse fechamento não qualifica o assistente nem inicia outro RD.

## Preparação antes de chamar o professor

- [ ] Entrega identificada por `git rev-parse HEAD` e `git status --short`.
  A base dos ensaios/revisão é `c6fa42d0314409610ab1dd4db14e4bfc9b55040f`;
  conferir os commits de entrega posteriores na branch `codex/block-5-validation`.
  Um clone somente da base não contém as mudanças B2-34/B2-35. Não fabricar
  autores/commits para completar a rubrica.
- [ ] Fazer o [comissionamento do runbook](../runbook.md#pilha-final-aiot-jobs-inferência-e-assistente):
  segredos, tokens InfluxDB restritos, conta proprietária, ambiente, `sim-lab-01`,
  catálogo e os dois UUIDs de proprietário. Baixar imagens/pesos previamente.
- [ ] Definir a função `coldsafe` do runbook nesta sessão de terminal. Ela conserva
  os cinco arquivos e perfis `aiot`/`simulator`. Todos os comandos abaixo usam
  essa composição; não trocar por `docker compose` da base no meio do percurso.
- [ ] Máquina ligada à tomada, Docker disponível e sem outra suíte/cálculo pesado.
  Verificar memória e espaço livre. A B2-34/R4 aprovou o Mac em AC/60 W; isso não
  comprova que a bateria foi a causa exclusiva das falhas anteriores.
- [ ] Preparar três contas privadas sugeridas no [README](../../README.md#usuários-de-demonstração),
  confirmar papéis com `/api/v1/auth/me` e manter senhas fora da tela/Git/docs.
  `admin` será dono do catálogo live; operador/viewer terão seus próprios ambientes.
  Não rebaixar o único admin: a API permite rebaixar o próprio usuário.
- [ ] Manter o simulador publicando previamente para acumular histórico causal
  live de **uma hora** e ter um modelo ativo válido. A ativação do modelo treinado
  na apresentação será demonstrada novamente. Conservar seed, dataset e versão
  anteriores como contingência identificada, sem chamá-los de resultado novo.
- [ ] Ensaiar a trajetória gradual da falha. Se necessário, definir previamente
  `SIMULATOR_STEP_SECONDS=60` no `.env` privado e recriar somente o simulador com
  a composição completa. Isso acelera desgaste, **não** as janelas UTC de features.
  Registrar essa condição no ensaio; reiniciar o processo apaga seu desgaste.
- [ ] Escolher limites de temperatura e preditivos demonstrativos no próprio
  ambiente, registrar valores originais e planejar a restauração. Não prometer
  alerta ao injetar falha: requer previsão válida, limiar e sequência de histerese.
- [ ] Vitor hugo conhece arquitetura/dados/IA e sua contribuição comprovável.
  Preparar navegador autenticado sem tokens no projetor; não exibir `.env`,
  configurações Compose resolvidas, cabeçalhos Authorization ou senhas.

Se faltar modelo/histórico, mostrar o estado indisponível e adiar a prova live;
não inserir fixtures antigas como se tivessem acabado de chegar pelo simulador.
O preparo de uma hora deve preceder a apresentação, pois `healthy` não aquece
features automaticamente. `up` na etapa 1 reaproveita containers saudáveis;
usar `down`/recriação do simulador reinicia sua trajetória física.

## Roteiro obrigatório, nesta ordem

| Passo | Ação e observação esperada | Fonte para conferir |
| --- | --- | --- |
| 1. Infraestrutura | Executar `coldsafe up -d --build --wait --wait-timeout 420` e `coldsafe ps -a`. Mostrar 14 contínuos saudáveis; inicializadores de brokers encerrados com zero. Preparo de pesos já concluído. Conferir `/health/live` e `/health/ready`. | [Compose base](../../compose.yaml), [runbook](../runbook.md), [B2-34/R4](../evidence/b2-34.json) |
| 2. Login e três papéis | Entrar separadamente como viewer, operator e admin; conferir papel atual. Viewer consulta, escrita deve ser recusada; operator altera apenas o seu cadastro/regras/LED; páginas administrativas exigem admin. Usar requisições autenticadas pelo OpenAPI para conferir recusa 403 quando a UI não oferece o botão. Outro proprietário recebe 404/recusa, mesmo sendo admin. | [Autenticação/papéis](../../backend/app/api/auth.py), [rotas v3](../../backend/app/api/aiot.py), [catálogo](../../backend/app/api/catalog.py) |
| 3. Sensores e MQTT | Voltar à conta proprietária live; mostrar catálogo com seis sensores, dois atuadores e um ventilador. `coldsafe logs --tail 20 simulator gateway` mostra operação sem revelar credenciais. Mostrar tópicos e fluxo MQTT → gateway; no dashboard conferir idade/valores mudando, não apenas conexão. | [Simulador](../../simulator/README.md), [contrato v3](../../contracts/aiot.md), [diagrama de telemetria](architecture.md#telemetria-recibo-e-entrega-web) |
| 4. FastAPI/REST | Abrir o link da API na interface ou `/docs` pela porta 5173. Mostrar contratos, autenticação, resumo/histórico do próprio dispositivo e respostas sem dados de terceiros. Não projetar o token ao autorizar. | [Proxy](../../frontend/nginx.conf), [rotas](../../backend/app/api/aiot.py), [OpenAPI local](http://localhost:5173/docs) |
| 5. RabbitMQ | Em `/messaging`, mostrar taxas, filas, horário da coleta e amostras privadas. Parar só writer, ver backlog aumentar, retomar e ver reduzir. Mostrar DLQ, inclusive vazia; não inventar erro para preencher contador. Detalhes e comandos abaixo. | [Ensaio de backlog](../runbook.md#mensageria-b2-16-parar-e-retomar-o-gravador), [teste real de observação](../../backend/tests/infra/test_observation_integration.py) |
| 6. Bancos e histórico | Conferir uma leitura live no InfluxDB (`telemetry_live`, `equipment_reading_v3`) e os seis campos de sensores. No PostgreSQL mostrar cadastro/regras/auditoria do próprio dispositivo. Consultar histórico via HTTP/UI e explicar a projeção SQL v3: não é leitura direta do Influx. Anotar event_id e UTC para cruzar evidências. | [Writer/teste](../../backend/tests/infra/test_writer_integration.py), [migrações](../../backend/migrations/README.md), [recibo e projeção](architecture.md#telemetria-recibo-e-entrega-web) |
| 7. WebSocket | Em `/dashboard`, observar gráficos, seis medições, freshness e indicadores por ID. Mostrar conexão WS no navegador e atualização real. Reconectar e conferir recuperação por HTTP; uma captura estática ou WS aberto não comprova dados novos. | [Cliente AIoT](../../frontend/src/features/monitoring/aiot-api.ts), [entrega API](../../backend/app/services/aiot_events.py) |
| 8. Atuadores | Ajustar temporariamente a regra de temperatura para cruzar o valor atual e acionar buzzer automaticamente; depois restaurar a faixa e conferir recuperação. Acionar LED pelo botão e mostrar `pending` → ACK → estado observado na telemetria seguinte. Ausência de ACK deve aparecer como `unconfirmed`, não sucesso. | [Comandos e regra](architecture.md#comando-ack-e-estado-observado), [borda/ACK](../../simulator/README.md#atuadores-e-ack--b2-10) |
| 9. Laboratório | Em `/laboratory`, informar seed, intervalo, equipamentos, sensores, falhas e condições de operação. Gerar ≥1.000.000 de linhas; acompanhar job até conclusão, quantidade/validação/dataset_id. HTTP 202 é aceite, não dataset pronto. Mostrar a pausa do assistente durante o job. | [Geração](../../backend/app/services/generation.py), [UI](../../frontend/src/features/laboratory/), [B2-34/R4](../evidence/b2-34.json) |
| 10. Treinamento/ativação | Em `/training`, selecionar o dataset concluído; treinar saúde e RUL. Mostrar MAE/RMSE/R², baseline, partições por equipamento, previsto × real e importância. Explicar rótulos sintéticos e ausência de vazamento. Ativar o pacote completo, aguardar estado concluído e conferir UUID/versão ativa; falha conserva o anterior. | [Métricas](../../backend/app/services/training.py), [features](../../backend/app/domain/features.py), [ativação](architecture.md#geração-treino-e-ativação) |
| 11. Falha/Insights/3D | Injetar `bearing_wear` pelo controle operacional autorizado abaixo. Acompanhar degradação gradual, previsão válida de saúde/RUL e tendência em `/insights`, versão/freshness, sequência de histerese e alerta. Em `/digital-twin`, selecionar ventilador/sensores/LED/buzzer e comparar IDs/valores com dashboard. Demonstrar ausência de dados pausando pelo controle MQTT, depois retomar sem reset. | [Controles](../../simulator/README.md#controles-autorizados-do-operador), [inferência/alertas](architecture.md#inferência-e-alertas), [cena](../../frontend/src/features/digital-twin/DigitalTwinScene.vue) |
| 12. LLM local | Após jobs terminarem e status pronto em `/assistant`, perguntar “Qual a situação do meu equipamento?” e uma pergunta específica baseada nos dados realmente presentes. Mostrar streaming, conclusão e referência à mesma falha/versão/idade. Perguntar sobre métricas/arquitetura e conferir a resposta contra a tela/documentos; se o resumo não contiver o dado, a resposta correta é declarar essa ausência. O LLM não controla LED nem consulta outros donos. | [Contexto autorizado](../../backend/app/services/assistant_context.py), [limites](architecture.md#assistente-local-e-coordenação-de-memória), [avaliação B2-32](tasks/B2-32.md), [R4](../evidence/b2-34.json) |

Papéis não compartilham ambientes. O único `sim-lab-01` provisionado pertence ao
admin live; não trocar a propriedade durante a prova. Para operador/viewer,
a ausência de leitura em seu ambiente é um resultado legítimo. Uma prova de
comando com telemetria nessas outras contas exigiria outro dispositivo com
credencial/ACL própria; este roteiro não afirma que ele existe.

### Backlog, DLQ e recuperação

Com o produtor ativo e a página Mensageria aberta:

```sh
coldsafe stop writer
coldsafe exec rabbitmq rabbitmqctl -q list_queues -p coldsafe name messages_ready messages_unacknowledged
coldsafe start writer
coldsafe logs --tail 30 writer
```

Espere o polling da página e compare horários/contagens. `consumers=0` pode ser
normal para `basic_get`; não usar esse número sozinho para diagnosticar parada.
Para observar zero estável após drenar, pare brevemente o simulador, depois
retome-o. Recibos e leitura persistida comprovam mais que fila vazia.
A UI não confirma, remove nem reenvia originais da DLQ. Uma mensagem sem
identidade privada comprovável não aparece nas amostras, embora conte no total.
O teste de observação vinculado na etapa 5 injeta mensagem inválida em pilha
**descartável** e comprova DLQ; se usar seu resultado histórico, declare isso.
Não execute esse teste contra recursos pessoais durante a apresentação.

Use `coldsafe start writer` se a demonstração for interrompida. Antes de um
`down/up`, anote um evento, cadastro, job e versão ativa. Preserve todos os
volumes e confira os mesmos IDs depois. O [runbook de recuperação](../runbook.md#reinício-e-recuperação-preservando-dados)
explica brokers/jobs/Ollama e a trava ambígua; não limpar locks com carregador vivo
nem editar status para contornar a coordenação.

### Conferir armazenamento sem mostrar segredos

No terminal privado, os comandos abaixo usam credenciais somente dentro dos
containers. Mostram registros da identidade demonstrativa `sim-lab-01`; confirme
antes que ela é a identidade escolhida na instalação. Não exibir detalhes JSON
de auditoria, payloads de outras contas ou saídas de configuração.

```sh
coldsafe exec -T postgres sh -ec \
  'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT d.id, d.environment_id, d.mqtt_device_id, d.is_active,
       r.temp_min_c, r.temp_max_c
FROM devices d JOIN environment_rules r ON r.environment_id = d.environment_id
WHERE d.mqtt_device_id = 'sim-lab-01';
SELECT a.event_type, a.occurred_at
FROM audit_events a JOIN devices d ON d.id = a.device_id
WHERE d.mqtt_device_id = 'sim-lab-01'
ORDER BY a.occurred_at DESC LIMIT 5;
SQL
coldsafe exec -T influxdb sh -ec \
  'exec influx query --org "$DOCKER_INFLUXDB_INIT_ORG" --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" "$1"' \
  sh 'from(bucket: "telemetry_live") |> range(start: -5m) |> filter(fn: (r) => r._measurement == "equipment_reading_v3" and r.device_id == "sim-lab-01") |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value") |> group() |> sort(columns: ["_time"], desc: true) |> limit(n: 2)'
```

Esse acesso é diagnóstico do operador da infraestrutura, não permissão da conta
Web nem credencial do writer (que só escreve). Para apresentar correlação, escolha
um `event_id` de leitura recente e compare com o histórico HTTP autenticado.

### Injetar falha e demonstrar falta de dados

Disponibilize `MQTT_SIMULATOR_OPERATOR_PASSWORD` somente como variável exportada
na sessão privada, conforme o [guia do simulador](../../simulator/README.md).
Não digite a senha literal no comando projetado e não carregue `.env` como script.
`-e` repassa o nome da variável; o valor não aparece nos argumentos do host.

```sh
coldsafe run --rm --no-deps --entrypoint python \
  -e MQTT_SIMULATOR_OPERATOR_PASSWORD simulator \
  -m simulator.control inject_fault --fault bearing_wear
```

A CLI confirma aceite MQTT, **sem ACK operacional**. Verifique o efeito nas
medições seguintes. Há também `imbalance`; seed reproduz medições, não UUIDs ou
horário. Não enviar labels/saúde/RUL verdadeiras pelo live. Aumento de desgaste
não garante que o limiar preditivo será atingido dentro do tempo da aula; a B2-36
deve medir a trajetória e ajustar a preparação, sem inventar aprovação.

Para ausência de dados, use os controles MQTT, preservando a trajetória de falha:

```sh
coldsafe run --rm --no-deps --entrypoint python \
  -e MQTT_SIMULATOR_OPERATOR_PASSWORD simulator -m simulator.control stop
# Aguarde mais de 30 s e confira freshness/indisponibilidade e animação congelada.
coldsafe run --rm --no-deps --entrypoint python \
  -e MQTT_SIMULATOR_OPERATOR_PASSWORD simulator -m simulator.control start
```

O processo continua saudável quando pausado por esse controle; a retomada
conserva desgaste/controles em memória. Já `coldsafe stop simulator` seguido de
`coldsafe start simulator` reinicia o processo e seu estado físico. Não apresentar
esse reset como recuperação física da falha. Confira telemetria nova antes do LLM.

## Perguntas para ensaiar e contribuições

- Por que MQTT na borda e RabbitMQ nos serviços? O que cada ACK confirma?
- Qual banco guarda cada dado? Por que recuperação HTTP v3 lê SQL?
- Como diferenciar pedido de LED, ACK e estado observado?
- Por que dividir treino/teste por equipamento e calcular features causais?
- Por que MAE/RMSE/R² sintéticos não comprovam precisão em equipamento real?
- O que ocorre sem modelo, sem histórico, sem leitura ou com consumidor parado?
- Como demonstrar que o 3D segue IDs/telemetria em vez de uma animação fixa?
- Como gerenciar 8 GB, pausa do assistente e três papéis privados?
- Quais fluxos vitor hugo implementou e quais evidências sustentam sua contribuição?

A conferência local `git shortlog -sne HEAD` em 23/10/2026 encontrou **74 commits
sob “vitor hugo”**, até `c6fa42d`. O usuário confirmou que **vitor hugo é o
único integrante e responsável pelo projeto**, coerente com a autoria registrada.
Os ensaios e a revisão descritos acima ocorreram antes dos commits de entrega.
O usuário autorizou posteriormente o commit e o push; conferir no histórico Git
a versão entregue.

## Respostas curtas para vitor hugo

- **MQTT e RabbitMQ:** MQTT liga o dispositivo à borda. RabbitMQ distribui eventos
  entre os serviços, com filas duráveis e reentrega. PUBACK/publisher confirm são
  transporte; não provam que o LED mudou nem que a leitura chegou ao banco.
- **Bancos:** InfluxDB guarda as séries live. PostgreSQL guarda contas, regras,
  auditoria, jobs/modelos e a projeção v3 usada pelo HTTP. SQLite é o diário do
  gateway; datasets/pacotes/pesos ficam nos volumes apropriados.
- **Comandos:** o pedido expressa o estado desejado; ACK correlacionado confirma
  a resposta da aplicação de borda; a próxima telemetria mostra o estado observado.
- **IA causal:** as janelas de 900/3600 s usam somente dados anteriores ao instante
  previsto. Dividir por equipamento evita testar com outro trecho do mesmo
  equipamento usado no treino. Rótulos verdadeiros ficam apenas no dataset offline.
- **Métricas:** MAE é erro absoluto médio, RMSE dá mais peso a erros grandes e
  R² compara a regressão com a variação do alvo. Comparar com baseline ajuda a
  avaliar utilidade no dataset; bons números sintéticos não certificam máquina real.
- **Falta de dados:** após 30 s, interface/predição indicam indisponibilidade e
  animação congela. Sem modelo ou sem uma hora causal, não inventamos saúde/RUL.
- **3D:** cada seleção conserva o ID do cadastro e mostra a leitura do mesmo
  backend do dashboard. Geometria e escalas visuais são ilustrativas; não são
  medição/calibração do equipamento físico.
- **Memória e LLM:** geração/treino são serializados e descarregam o modelo de
  linguagem antes do cálculo. O assistente recebe resumo privado somente leitura,
  não executa comandos e deve declarar quando o resumo não contém a informação.
- **Autoria:** vitor hugo é o único integrante informado e o autor registrado no
  Git. Na apresentação, relacionar cada fluxo ao código, ao commit e à evidência
  real; uso de ferramentas não substitui saber explicar as decisões.

## Registro de ensaio — preencher na B2-36

O quadro abaixo preserva o estado da revisão B2-35. O encerramento posterior da
[B2-36](tasks/B2-36.md), com evidências, limites e confirmação pelo usuário da
correção final do assistente, está registrado no cartão; não representa nova
execução automatizada ou medição dos campos históricos abaixo.

| Campo | Estado nesta B2-35 |
| --- | --- |
| Data, versão final e máquina | Ensaio pendente; revisão documental em 23/10/2026 |
| Passos 1–12, resultado observado e evidência nova | Pendentes; não executados por esta tarefa |
| Duração total e de geração/treino/LLM | A medir; tempos anteriores são referências históricas |
| Catálogo/seed/passo/limiares/modelo/contas usados | A registrar sem credenciais; identificar IDs autorizados |
| Falha → previsão → histerese → alerta → 3D → resposta LLM | Trajetória live completa ainda a ensaiar |
| Outro integrante seguiu a instalação | Não executado; revisão técnica independente não substitui teste humano |
| Bloqueadores, correções e nova rodada | A registrar e repetir após mudanças materiais |

As [evidências B2-34](../evidence/b2-34.json) registram stack real e regressão,
mas não substituem o ensaio integral da falha live. A [B2-32](tasks/B2-32.md)
avaliou respostas com dados preparados declarados. Exponha essas diferenças e
os limites em vez de tratar inclusão de biblioteca ou captura antiga como prova.
