# Apresentação final — 16/11/2026

Apresentação presencial em 2026-11-16, diretamente na aplicação, sem slides.
**Roteiro revisado na B2-35 em 23/10/2026; ensaio completo B2-36 ainda pendente.**
A ordem abaixo reproduz o [enunciado do professor](../history/assignment.md).
Resultados anteriores são identificados como evidência histórica; este documento
não afirma que a demonstração foi executada novamente.

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
| 1. Infraestrutura | Executar `coldsafe up -d --build --wait --wait-timeout 300` e `coldsafe ps -a`. Mostrar 14 contínuos saudáveis; inicializadores de brokers encerrados com zero. Preparo de pesos já concluído. Conferir `/health/live` e `/health/ready`. | [Compose base](../../compose.yaml), [runbook](../runbook.md), [B2-34/R4](../evidence/b2-34.json) |
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

## Registro de ensaio — preencher na B2-36

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
