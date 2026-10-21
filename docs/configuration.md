# Configuração e segredos

Esta página separa configuração versionável de credenciais locais.

## Versões do projeto

A fonte principal é a [matriz de versões](version-matrix.md), com runtimes,
manifestos, locks e dependências previstas. Não repetir a matriz nesta página.

O computador pode ter outra versão instalada, mas desenvolvimento, Docker e CI devem convergir para as versões registradas. Não use tags `latest`, intervalos abertos ou atualizações automáticas silenciosas nos manifestos finais.

## Criar a configuração local

O procedimento de criação está no [runbook](runbook.md#2-criar-a-configuração-local).
Esta página explica valores e permissões. Preencha somente os arquivos locais
`.env` e `firmware/include/secrets.h`.

Use `python3 scripts/generate-secrets.py` para criar/completar o `.env` com
segredos aleatórios distintos, sem imprimir valores ou sobrescrever credenciais
existentes. O arquivo fica com `0600`; o script versionado não contém segredos.
`INFLUXDB_TOKEN` continua dependendo da autorização restrita criada pelo banco.
`INFLUXDB_WRITER_TOKEN` também fica vazio até criar autorização InfluxDB:
somente escrita no bucket `telemetry_live`, exclusiva do gravador B2-12.
O build Docker do frontend usa a mesma origem; `VITE_API_BASE_URL` é apenas uma
opção do Vite local. Alterar uma variável no container não recompila o JavaScript.

## Valores que precisam ser definidos localmente

No `.env`:

- `MQTT_BACKEND_PASSWORD`
- `MQTT_DEVICE_PASSWORD`
- `MQTT_DEVICE_02_PASSWORD` (distinta da primeira)
- `INFLUXDB_TOKEN`
- `DOCKER_INFLUXDB_INIT_USERNAME`
- `DOCKER_INFLUXDB_INIT_PASSWORD`
- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`
- `POSTGRES_PASSWORD`
- `AUTH_JWT_SECRET` (chave aleatória privada, no mínimo 32 caracteres)

A infraestrutura exige também as onze senhas `RABBITMQ_*_PASSWORD` listadas em
`.env.example`, aleatórias, distintas e com pelo menos 32 caracteres.
São identidades próprias por serviço, sem `guest` ou administrador de aplicação.
O bootstrap gera hashes num volume privado; não escreva senhas/definições
geradas no Git. Consulte [infra RabbitMQ](../infra/rabbitmq/README.md) para
permissões e inicialização. A entrega não alterou o `.env` pessoal; os testes
criam credenciais exclusivamente temporárias.

A chave JWT assina os novos tokens. Gere uma vez, fora do Git, e conserve o
valor entre reinícios; não reutilize senhas dos bancos. O Compose exige esse
campo e o backend recusa chave ausente/curta. `.env.example` contém apenas o
campo vazio. Após a entrega B2-06, o usuário solicitou a configuração local:
a chave JWT foi acrescentada ao `.env` privado, preservando as demais credenciais.
Trocar a chave invalida os JWT emitidos anteriormente; revogação normal usa
o registro de sessões no PostgreSQL, sem precisar trocar a chave.

`POSTGRES_DB` e `POSTGRES_USER` têm valores locais padrão (`coldsafe`). O
backend usa `POSTGRES_HOST=postgres` e a porta interna `5432`; no Compose,
o PostgreSQL não expõe porta ao host. Use senhas distintas para PostgreSQL,
MQTT e InfluxDB.

No `firmware/include/secrets.h`, configure a senha do primeiro ESP32 e a do
segundo conforme [`firmware/README.md`](../firmware/README.md). O segundo usa
`coldsafe-device-02`; o primeiro usa `coldsafe-device`. O backend usa
`coldsafe-backend`. A ACL restringe telemetria, comandos e confirmações por
identidade. Não compartilhe usuários ou senhas entre os dispositivos.

Não altere esses usuários nem `MQTT_TOPIC` apenas no `.env`: eles fazem parte do
contrato da ACL. Uma mudança futura precisa atualizar configuração, ACL, firmware e
testes em conjunto.

O SSID `Wokwi-GUEST`, o host `host.wokwi.internal` e os identificadores
`esp32-lab-01`/`esp32-lab-02` são configurações demonstrativas, não credenciais.

## Simulador opcional B2-09/10

O perfil `simulator` usa `MQTT_SIMULATOR_PASSWORD` e
`MQTT_SIMULATOR_OPERATOR_PASSWORD`, geradas pelo mesmo script idempotente.
Campos vazios não criam essas contas no broker e não impedem a pilha v1/v2.
Para habilitar o simulador, forneça a senha do dispositivo e um `catalog.json`
válido em `SIMULATOR_CATALOG_DIR` (padrão `simulator/local`, fora do Git/build).
O arquivo é cadastro local de borda; use IDs reais de ambiente/dispositivo do
PostgreSQL quando integrar ao produto. Equipamento/sensores/atuadores ainda
são registrados localmente, sem API/tabelas. O gateway B2-11 cruza dispositivo
ativo, ambiente e proprietário esperado no PostgreSQL; não confia só nesses IDs.
A B2-10 usa também `MQTT_GATEWAY_PASSWORD` para a conta `coldsafe-gateway`,
com publicação apenas dos comandos v3 do simulador e leitura de seus ACKs e
telemetria. O gerador cria a senha quando ausente, sem rotacionar valores.
É uma credencial distinta de `RABBITMQ_GATEWAY_PASSWORD`. O perfil `aiot` inicia o
serviço da B2-11 e exige `GATEWAY_OWNER_USER_ID`, UUID do dono cadastrado no PostgreSQL,
além das senhas dos dois brokers e do mesmo catálogo privado. Seu diário persistente
fica no volume `gateway-state`; não o apague em reinícios. Operação, teste isolado
e limite do diário estão em [`gateway/README.md`](../gateway/README.md).
Campos MQTT vazios não provisionam a conta nem habilitam o gateway.
Preparação, permissões, ritmo de simulação e comandos do operador estão em
[`simulator/README.md`](../simulator/README.md). Nenhum segredo pessoal foi
alterado na execução B2-09; integração usa credenciais descartáveis.

## Ollama local e memória B2-30

O overlay opcional `compose.ollama.yaml` deve acompanhar `compose.jobs.yaml`.
Ele passa `OLLAMA_URL=http://ollama:11434` à API, aos dois workers pesados e ao
coordenador `llm`. Sem essa variável, o runtime anterior permanece desativado
para LLM. Fora do Compose, só são aceitos HTTP em `ollama` ou loopback, sem
credenciais, caminho ou query; não apontar para servidores de nuvem.

Prepare os pesos **antes da apresentação**, com `ollama` e `llm` parados:

```sh
docker compose -f compose.yaml -f compose.jobs.yaml -f compose.ollama.yaml run --rm --no-deps ollama-prepare
```

Somente esse serviço temporário possui saída de rede, baixa pesos públicos e
grava em `ollama-data`; não recebe credenciais da aplicação nem monta datasets.
Não executar o preparo em paralelo ao runtime sobre o mesmo volume.
O runtime monta os pesos somente para leitura, não publica porta e usa apenas
a rede interna `coldsafe-llm`. `OLLAMA_NO_CLOUD=1`, ausência de API key,
transporte sem proxy/redirecionamento e ausência de saída de rede evitam
envio de dados a serviços externos. O primeiro download exige internet; a
operação posterior usa o volume local, inclusive após recriar o container.

Para habilitar junto dos overlays AIoT/inferência já escolhidos:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml -f compose.inference.yaml -f compose.ollama.yaml config --quiet
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml -f compose.inference.yaml -f compose.ollama.yaml up -d --build ollama llm backend generation training frontend
```

O modelo é `llama3.2:1b-instruct-q4_K_M`, variante explícita Llama 3.2 **1B Q4**
indicada pelo ensaio B2-03. A tag curta `llama3.2:1b` usa Q8; não foi usada como
alias silencioso. Ollama `0.40.3`, CPU, contexto de 1.024 tokens, duas threads,
uma requisição e um modelo por vez; limite de 2 GiB/2 CPUs. Esses limites não
certificam a capacidade da pilha completa, reservada à B2-33.

`python -m backend.app.llm_worker` tenta pré-carregar com prompt vazio sob o
mesmo lock PostgreSQL que serializa geração/treino. Um marcador durável de
pré-carga impede o início do cálculo mesmo se a sessão do coordenador cair
enquanto o Ollama ainda estiver carregando. Antes de iniciar o cálculo,
o worker descarrega os modelos residentes e confirma `/api/ps` vazio.
Se não confirmar, conserva o job aguardando e a entrega AMQP pendente, sem
iniciar o handler nem gastar retries por indisponibilidade do Ollama.
O coordenador consulta novamente a cada dois segundos e recarrega após o job,
inclusive quando o handler falha. Jobs ainda `running` impedem a recarga mesmo
se o lock da sessão foi perdido. Um job órfão conserva o LLM pausado: retome
o worker/entrega original e confira seu estado; não altere status manualmente
para forçar recarga enquanto um cálculo puder estar vivo.

Se houver timeout, interrupção do coordenador ou queda da sessão **durante a pré-carga**, o registro em
`llm_memory_guard` permanece e bloqueia jobs e novas cargas. `/api/ps` vazio
não prova ausência de carregamento em curso nessa situação. Para recuperar,
pare `llm`, reinicie `ollama` para encerrar qualquer loader e só então remova
o marcador via PostgreSQL; volte a iniciar `llm`. Preserve os mesmos arquivos
`-f` usados na instalação. Não limpe o marcador com o carregador ainda vivo.
No shell SQL do banco, depois dessas duas ações:

```sql
DELETE FROM llm_memory_guard WHERE id = 1;
```

Esse procedimento remove apenas a trava operacional, sem apagar jobs/modelos.
O sistema prefere aguardar intervenção a arriscar sobreposição de memória.

`GET /api/v3/llm/status` exige sessão e informa somente o estado da infraestrutura,
sem IDs ou dados de jobs de outras contas. Laboratório e Treinamento explicam
carregamento, pausa para liberar memória, ausência dos pesos e indisponibilidade.
Ollama indisponível não derruba a readiness geral do monitoramento.
Para diagnóstico: `docker compose ... logs llm ollama` e `docker compose ... exec ollama ollama ps`.
Modelo ausente exige repetir o preparo; reinício normal não baixa pesos.
Conversa/contexto autorizado/streaming pertencem às B2-31/B2-32.

Sem dependência Python/Node nova, Redis ou Celery. A migração 012 acrescenta
somente o marcador de coordenação, sem alterar dados de usuários/telemetria.
Dependência de
infraestrutura adicionada: imagem Ollama e pesos públicos persistentes.
Semântica de pré-carga/descarga: [FAQ oficial](https://docs.ollama.com/faq).
Quantização: [biblioteca oficial](https://ollama.com/library/llama3.2/tags).

## Jobs assíncronos B2-17

Opt-in separado, sem modificar o ambiente pessoal automaticamente:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml up -d --build backend generation training
```

Antes de usar em dados importantes, seguir backup/restauração no
[guia de migrações](../backend/migrations/README.md); o runner aplicará até a 012.
O exemplo combina AIoT existente com jobs, mas jobs não exigem catálogo/dispositivo.
As credenciais `RABBITMQ_API_PASSWORD`, `RABBITMQ_GENERATION_PASSWORD` e
`RABBITMQ_TRAINING_PASSWORD` já constam de `.env.example` e da topologia B2-07.
API publica usando somente sua identidade; cada worker recebe somente a própria
credencial AMQP. Não compartilhar senhas entre papéis. Workers reaproveitam imagem,
ambiente PostgreSQL, usuário sem privilégios, filesystem read-only e rede interna
do backend. Não publicam portas. As verificações de vida dos executores ficam
para integração operacional B2-33; o healthcheck HTTP herdado é desativado neles.

API instala as rotas de jobs e de consulta privada de datasets quando a sua credencial está presente; sem ela,
o comportamento anterior permanece. `202` significa solicitação persistida;
broker indisponível deixa a publicação na outbox e não exige esperar no HTTP.
Consultar o job mostra o estado durável, mesmo com worker parado.
Readiness geral não depende do publicador de jobs: a API pode enfileirar na outbox
durante uma indisponibilidade AMQP. As demais dependências de readiness permanecem.

Workers podem ser executados com o ambiente do backend por
`python -m backend.app.job_worker --role generation` ou `--role training`.
Geração massiva está instalada na B2-18; B2-23 instala preparo e os dois treinos
em filhos separados/sequenciais, sem ativar o pacote no monitoramento.
`JOB_ARTIFACT_ROOT` define a raiz interna, padrão `/app/artifacts`. O overlay
monta o volume persistente `job-artifacts`: RW só para geração, RO para API/treino.
A imagem prepara proprietário/permissões para seu usuário sem privilégios.
Se trocar a raiz, ajuste também a montagem; não aponte para buckets/volumes live.
Geração tem limite de 512 MiB/1 CPU; não é garantia de capacidade da pilha completa.
`TRAINING_ARTIFACT_ROOT` define a raiz de resultados, padrão
`/app/training-artifacts`: volume separado `training-artifacts`, RW somente no
treinamento e RO na API. O worker de treino tem limite inicial de 1 GiB/1 CPU;
o ensaio HTTP/AMQP/browser não equivale à medição de toda a pilha nesse limite.
Fora do Compose, forneça as duas raízes acessíveis aos respectivos processos.
Retomada recalcula em nova tentativa e preserva o contador; pastas parciais e
preparos completos são conservados, sem expurgo automático. Não apague arquivos
de jobs ativos nem pacotes referenciados por `models`.
Formato, retomada, limpeza de órfãos e benchmark estão no
[backend](../backend/README.md#geração-offline-b2-18).

O bloqueio global é de sessão PostgreSQL e vale entre geração e treino de todas
as contas. Worker interrompido deixa checkpoint no banco e entrega sem ACK;
reinício da geração repete deterministicamente em diretório novo e preserva o contador.
Não reiniciar PostgreSQL enquanto houver cálculo real: a perda da sessão libera
o lock; o executor só detecta isso no próximo checkpoint. Esta tarefa não prova
alta disponibilidade durante falha do coordenador.

Progresso HTTP/SSE e parâmetros estão no
[contrato B2-17](../contracts/aiot.md#jobs-http-e-progresso-sse--b2-17).
O stream lê estado privado no banco a cada segundo, revalida sessão e termina ao
revogar acesso ou concluir. Solicitações e eventos AMQP permanecem duráveis;
outbox não tem expurgo automático. Não remover solicitações de jobs ativos.

Na B2-19, `/laboratory` no frontend permite gerar e inspecionar datasets privados.
Reconstrua também `frontend` para disponibilizar a página. O formulário exige
admin; consultas ao artefato usam a montagem RO já existente na API. Não é
necessária nova variável, porta ou dependência. `?job=UUID` na URL recupera o
estado após recarga; salve essa URL para retomar o mesmo job. Sem a configuração
de jobs acima, a página informa erro de consulta/execução; ela não ativa workers.
Contrato de resumo/amostra em [datasets](../contracts/aiot.md#consulta-privada-de-datasets--b2-19).

Na B2-23, `/training` permite selecionar um dataset concluído da conta ou seguir
o link do Laboratório. Apenas admin envia o treinamento; `?job=UUID` recupera
o acompanhamento e os resultados após recarga. A API precisa das duas montagens
RO descritas acima. Sem o worker `training`, o job permanece enfileirado.
Métricas são de regressão offline; concluir o job ou vencer a baseline não ativa
um modelo no monitoramento. Contrato em [B2-23](../contracts/aiot.md#resultados-e-diagnósticos-de-treinamento--b2-23).

## Ativação de modelos B2-24

O overlay de jobs também define `models`, com `RABBITMQ_INFERENCE_PASSWORD`
(credencial já prevista na topologia), `TRAINING_ARTIFACT_ROOT` e volume de treino
somente leitura. Não precisa catálogo live, MQTT, porta publicada ou biblioteca
nova. Limite inicial: 512 MiB/1 CPU, sujeito à medição da pilha na B2-33.

Antes de habilitar, reconstruir o bootstrap e atualizar RabbitMQ preservando
volumes, conforme [infra](../infra/rabbitmq/README.md), para instalar a décima
fila `coldsafe.model-activation` e seu ACL. Rebuild coordenado dos consumidores
também leva a correção do schema para `features_version` com `+`. O backend
atualizado de Mensageria espera as dez filas. Depois, no ambiente já configurado:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml up -d --build backend models
```

Fora do Compose: `python -m backend.app.model_worker`, com configuração PostgreSQL,
RabbitMQ e volume RO próprios. A API usa apenas `RABBITMQ_API_PASSWORD` para
publicar pedidos; o worker usa apenas sua identidade `inference`. As rotas ficam
disponíveis junto do opt-in dos jobs. `202` conserva pedido mesmo com worker/broker
parado; consulte status antes de enviar novamente, pois só uma ativação pode ficar
pendente por dono. A [API privada](../contracts/aiot.md#ativação-implementada--b2-24)
lista modelos, registra ativação e informa versão ativa/erros. A interface web de
ativação não faz parte desta entrega.

Retomada do mesmo pedido em `loading` recarrega o pacote. Se o broker esgotar o
limite de redelivery, faça recuperação manual da mensagem original da DLQ, com
mesmos IDs/propriedades; não exclua outbox/ativação para liberar outro pedido.
Para voltar à versão anterior, envie um novo pedido usando o ID anterior; não
edite `active_models` por SQL. Não apagar pacotes referenciados, inclusive antigos.
Registro ativo é durável; reidratação e inferência online ficam para B2-25.

## Inferência ao vivo B2-25

Opt-in sobre AIoT/jobs, com o mesmo catálogo e proprietário já comissionados:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml -f compose.inference.yaml config --quiet
docker compose -f compose.yaml -f compose.aiot.yaml -f compose.jobs.yaml -f compose.inference.yaml up -d --build backend models frontend
```

Esses comandos são instruções para implantação autorizada; os ensaios desta
entrega usam infraestrutura descartável. O último overlay substitui somente o
comando do serviço `models`: não inicie outro worker de ativação concorrente por
engano. Preserva 512 MiB/1 CPU e artefatos RO, acrescentando catálogo RO em
`/catalog/catalog.json` a partir de `SIMULATOR_CATALOG_DIR` e dono
`AIOT_OWNER_USER_ID` a partir de `GATEWAY_OWNER_USER_ID`. Não publica portas nem
precisa de nova biblioteca/credencial: usa `RABBITMQ_INFERENCE_PASSWORD` existente.
O runner aplica migração aditiva 010; seguir backup no guia de migrações antes.

Fora do Compose, `python -m backend.app.inference_worker` exige configuração
PostgreSQL/RabbitMQ, raiz privada de treino, `AIOT_CATALOG_PATH` e
`AIOT_OWNER_USER_ID`. Não precisa ativar consumidores da API no mesmo processo.
O frontend deve ser reconstruído em modo AIoT para exibir previsão. Backend/writer/
gateway precisam estar operantes para a fonte e sua prova de persistência chegarem
ao WebSocket, conforme a integração anterior; este overlay não os comissiona.

Ativação segue a API B2-24. O worker restaura o modelo ativo ao iniciar e troca
sem reinício; pacote reprovado/incompleto não muda a versão anterior. Sem histórico
prévio, o padrão 900/3600 s exige uma hora de coleta. Estados de indisponibilidade
são informados, sem inventar zero. Não apagar `inference_events` para acelerar
warm-up/retry: histórico, IDs e saída formam a deduplicação durável.

Consulta é limitada à janela e até 10.000 registros incluindo âncora; excesso gera
`invalid_features`. Disco cresce sem expurgo automático, e JSON/histórico têm custo
de I/O por previsão. Revogar dono/desativar dispositivo fecha a publicação e pode
encerrar/reiniciar esse runtime; corrigir o comissionamento antes de retomar.
Perdas repetidas de conexão ainda podem esgotar redelivery e exigir recuperação
manual da mensagem original na DLQ. Ver [contrato](../contracts/aiot.md#inferência-ao-vivo-implementada--b2-25).

## API AIoT opcional B2-13

Depois de preparar catálogo, proprietário, brokers e token exclusivo do writer,
habilite a API com o overlay explícito:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml --profile aiot --profile simulator config --quiet
docker compose -f compose.yaml -f compose.aiot.yaml --profile aiot --profile simulator up -d --build frontend backend gateway writer simulator
```

O overlay define `AIOT_ENABLED=true`, `AIOT_CATALOG_PATH=/catalog/catalog.json`,
`AIOT_OWNER_USER_ID` a partir de `GATEWAY_OWNER_USER_ID`, e injeta somente as
senhas AMQP `commands`/`delivery` e a credencial HTTP `monitor` no backend. Monte o mesmo catálogo privado do
gateway/writer; `WRITER_OWNER_USER_ID` deve ser o mesmo dono. Fora do Docker,
informe esses campos e `RABBITMQ_HOST/PORT`. Configuração incompleta é recusada.
Sem overlay a API v3 permanece desabilitada e o backend conserva v1/v2.

Na B2-14, o overlay também passa `VITE_AIOT_ENABLED=true` ao build do frontend.
Reconstrua `frontend` com o mesmo overlay para conectar a tela ao stream/REST v3.
A variável não altera um JavaScript já compilado. Em desenvolvimento local,
defina `VITE_AIOT_ENABLED=true` e `VITE_API_BASE_URL` antes de iniciar Vite.

Não há token InfluxDB adicional na API: seu estado/histórico processado v3 é
consultado no PostgreSQL; `telemetry_persisted` comprova a gravação pelo writer.
O token legado conserva as permissões anteriores. Na instalação RabbitMQ já
existente, as novas ACLs/bindings de recibos precisam ser importadas pelo bootstrap;
não apague volumes. Consulte [infra RabbitMQ](../infra/rabbitmq/README.md).
Esta entrega valida uma pilha descartável, sem modificar as credenciais pessoais.

## Mensageria B2-15

`RABBITMQ_MONITOR_PASSWORD` é a nova credencial exclusiva do backend para
consultar métricas HTTP do RabbitMQ. O gerador preenche essa chave se ausente,
sem mudar os demais segredos. O bootstrap cria `coldsafe-monitor` com tag
`management` e sem permissão de configurar/publicar/consumir mensagens.
Em instalações existentes, reexecute bootstrap/import preservando volumes;
não basta inserir a chave no backend sem provisionar o usuário no broker.

Para atualizar uma instalação existente já configurada, em uma janela de
manutenção (o restart interrompe conexões brevemente):

```sh
python3 scripts/generate-secrets.py
docker compose run --rm --no-deps --build rabbitmq-init
docker compose restart rabbitmq
docker compose -f compose.yaml -f compose.messaging.yaml up -d --build --no-deps backend frontend
```

Os comandos preservam volumes e valores existentes. `compose.messaging.yaml`
habilita métricas e o observador B2-16, conservando o modo do dashboard;
não exige catálogo nem habilita o modo AIoT completo. Não execute `down --volumes`
na pilha pessoal.

`compose.messaging.yaml` injeta a senha e `RABBITMQ_MANAGEMENT_PORT=15672` no backend;
o host é `RABBITMQ_HOST`. Nenhuma variável `VITE_*` contém a credencial e nenhuma
porta adicional é publicada. Fora do Compose, esses três campos habilitam a rota
de métricas independentemente dos consumidores AIoT. Sem a senha configurada,
a rota não é instalada (404); a página informa a falha e a operação legada continua separada.
O overlay `compose.aiot.yaml` também inclui essas variáveis para quem já ativou
o percurso AIoT completo. Ao atualizar a instalação, conserve o overlay escolhido.

Acesse `/messaging` com conta **admin** ColdSafe. As filas são compartilhadas,
por isso os números são agregados de infraestrutura: viewer/operator não os
consultam e nem administradores recebem corpos de mensagens. Cadastro público
não permite escolher admin. Não promova contas nem altere credenciais de produção
para testar; o harness da B2-15 cria contas e infraestrutura descartáveis.

### Amostras privadas B2-16

Os dois overlays também fornecem `RABBITMQ_PORT=5672` e a senha já existente
`RABBITMQ_OBSERVABILITY_PASSWORD`. O backend usa `coldsafe-observability` para
consumir somente `coldsafe.observability`. O bootstrap atualizado precisa ser
importado para copiar também `coldsafe.dlx` e `coldsafe.jobs.unrouted` nessa fila;
o procedimento acima preserva os originais e os volumes.

`GET /api/v3/messaging/messages` exige admin e filtra os resumos pelo proprietário
atual do dispositivo/ambiente no PostgreSQL. O corpo bruto nunca é devolvido.
As métricas globais e as amostras privadas podem, portanto, ter contagens diferentes.
Sem credencial de observação, o painel informa observador desconectado.
O observador independe de `AIOT_ENABLED`; os dois overlays continuam opcionais.

São até 100 resumos recentes de eventos e 100 de mensagens mortas em memória,
por processo, compartilhados entre proprietários antes do filtro de acesso.
Reiniciar o backend apaga essas amostras; não apaga a DLQ. As cópias no broker
têm teto de 8 MiB, descartando as mais antigas quando cheio, sem retorno à DLX.
Isso é amostragem operacional, não arquivo histórico nem inventário completo da DLQ.
Originais anteriores à instalação dos bindings não são copiados retroativamente.
Para ensaio de parada/retomada e limites, veja o [runbook](runbook.md#mensageria-b2-16-parar-e-retomar-o-gravador).

## Permissões do token InfluxDB

O gravador v3 usa `INFLUXDB_WRITER_TOKEN`, distinto dos tokens abaixo, sem leitura
e sem acesso a `telemetry` ou a dados sintéticos. Configure `WRITER_OWNER_USER_ID`
com o proprietário esperado do cadastro compartilhado com o gateway.
Criação do bucket live, retenção, autorização e execução opcional estão em
[`writer/README.md`](../writer/README.md). A tarefa não provisiona credenciais na pilha pessoal.

`INFLUXDB_TOKEN` deve ser um token exclusivo do backend, com leitura e escrita
somente no bucket `telemetry`. Não reutilize `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`:
ele possui privilégios administrativos e deve ficar reservado à administração.

Com a CLI do container autenticada para administração, consulte o ID do bucket
usando `docker compose exec influxdb influx bucket list --name telemetry`.
Crie uma autorização com `influx auth create`, organização `coldsafe`, descrição
`coldsafe-backend-telemetry` e opções `--read-bucket` e `--write-bucket` apontando
para esse ID. Não use `--all-access` ou `--operator` para o backend.

Guarde o token retornado somente em `INFLUXDB_TOKEN` no `.env` local. Não copie o
valor para documentação, commits, Notion ou mensagens. Depois execute
`docker compose up -d --no-deps backend` para carregar a configuração alterada;
editar o `.env` não atualiza automaticamente o ambiente do container existente.

### Revisão de segurança da CS-36 — 10 de setembro de 2026

- O backend carregou o novo token, diferente do token administrador.
- A autorização contém somente leitura e escrita no bucket `telemetry`.
- Gravação e consulta reais passaram usando o token do backend, com um registro
  temporário em uma medição exclusiva de teste; o registro foi removido e sua
  ausência foi confirmada após a validação.
- A consulta à autorização administrativa com o token do backend retornou `401`.
- `/health/ready`, `/api/v1/monitoring/summary` e
  `/api/v1/readings?device_id=esp32-lab-01&period=24h&limit=1` retornaram `200`.
- Clientes MQTT anônimos foram recusados; o dispositivo pôde publicar somente em
  `coldsafe/v1/telemetry`; o backend pôde ler telemetria e `$SYS/#`, mas não
  publicar no tópico do dispositivo.
- Os arquivos `passwords` e `acl` foram gerados no volume privado do Mosquitto
  com owner `1883:1883` e modo `0600`. Uma composição criada com volumes novos
  iniciou sem avisos de owner, grupo ou leitura global.
- O Gitleaks `8.29.0` examinou os 32 commits do repositório com saída redigida e
  não encontrou vazamentos.
- O `pip-audit` `2.10.1` não encontrou vulnerabilidades conhecidas nos locks de
  produção e desenvolvimento do backend.
- `npm audit` e `npm audit --omit=dev` não encontraram vulnerabilidades conhecidas
  no frontend.

A CS-36 está concluída para o escopo acadêmico local. Os scanners representam a
base de vulnerabilidades conhecida na data da execução e devem ser repetidos
antes de futuras entregas. A troca das credenciais continua sendo uma operação
local e não é versionada.

## Correção de segurança do urllib3 — 14 de outubro de 2026

Concluída localmente: `urllib3 2.7.0` foi atualizado para `2.8.0`, versão que
corrige os avisos [GHSA-vxq7-64xx-v4gw](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw),
[GHSA-gh4c-6fx4-qh6g](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g)
e [GHSA-8988-9cw3-xx77](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77).
A dependência já era utilizada pelo `influxdb-client`; passou a ser fixada
explicitamente no manifesto, além dos dois locks, para conservar a versão
validada em instalações futuras. Nenhuma biblioteca nova foi adicionada;
nenhuma outra versão dos locks mudou.

Resultado desta execução (separado da evidência histórica da CS-36):

- `pip-audit`: três vulnerabilidades antes; zero conhecidas depois, auditando
  separadamente produção e desenvolvimento.
- Suíte backend: **450 passaram, 103 ignorados, cobertura de 80,64%** com
  medição de ramos. Os testes ignorados dependem de ambientes/serviços opcionais.
- Integração Docker descartável: **dois testes passaram**, incluindo gravação
  MQTT/InfluxDB, consulta histórica, autenticação, WebSocket e reinício.
- O teste do `.env.example` tinha uma lista antiga de campos; a falha também
  ocorreu com `urllib3 2.7.0`. A expectativa agora inclui os 16 campos existentes
  de RabbitMQ/simulador/gateway e verifica que suas senhas e a do PostgreSQL
  continuam vazias no exemplo. O arquivo `.env.example` não foi alterado.
- Imagem backend reconstruída e somente seu container recriado; `urllib3 2.8.0`
  confirmado em execução. Configuração e credenciais mantidas, volumes
  preservados e os outros cinco containers ativos sem recriação.
- `.venv` local atualizada somente em `urllib3`; verificação de compatibilidade
  das dependências passou. Readiness, docs e OpenAPI pelo frontend retornaram `200`.

Arquivos, comandos, versão Git de base, hashes, revisão estática por subagente,
limitações e checkpoint estão na [evidência da correção](evidence/urllib3-security-fix.json).
O aceite local é atualização aplicada, auditorias sem os três avisos e testes
de compatibilidade aprovados; todos foram atendidos. O resultado não certifica
ausência de todas as falhas da aplicação: a auditoria consulta os avisos conhecidos
na data. Os ataques dos avisos não foram reproduzidos, e os 103 testes opcionais
não foram habilitados em conjunto.

Checkpoint da validação anterior à publicação: base
`a7f6ea4e41c8d35699dd29855a9d037724907117`, branch
`codex/block-5-validation`; correção local validada, com commit/push autorizados
pelo usuário. Para retomar, consultar o histórico Git e comparar `HEAD` com a
branch remota para confirmar a publicação. A B2-11 não foi iniciada.

## Regras obrigatórias

1. Nunca colocar valores reais em `.env.example` ou `secrets.example.h`.
2. Nunca remover `.env` ou `secrets.h` do `.gitignore`.
3. Não registrar valores secretos em logs, mensagens de erro ou capturas de tela.
4. Credenciais de demonstração não podem ser reutilizadas em ambiente real.
5. Configuração ausente, vazia ou ainda contendo `REPLACE_WITH_...` deve impedir readiness.
6. Mensagens de erro podem indicar qual variável está ausente, mas nunca revelar seu valor.

## Instalar as dependências de teste

Para reproduzir exatamente o ambiente validado:

```bash
python3.13 --version
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock.txt
```

O primeiro comando precisa mostrar exatamente `Python 3.13.15`. Se `python3.13` não existir, instale o runtime antes de recriar a `.venv`; usar outra versão não é uma reprodução exata do ambiente planejado.

`requirements-dev.txt` lista apenas as dependências escolhidas diretamente; o arquivo de lock fixa também as dependências transitivas.
