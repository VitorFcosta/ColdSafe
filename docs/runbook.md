# Runbook local do ColdSafe

Execute os comandos a partir da raiz do repositório. Escolha o procedimento
de acordo com o estado da instalação.

| Situação | Procedimento |
| --- | --- |
| Checkout novo, sem conta, catálogo ou pesos | Siga as seções 1–5 e continue em [Pilha final](#pilha-final-aiot-jobs-inferência-e-assistente). A base com `-f compose.yaml` permite cadastrar o proprietário antes de ligar a coleta v3. |
| Conta, catálogo, tokens e pesos já preparados | Execute `docker compose up -d --wait --wait-timeout 420` e [confira o funcionamento](#pilha-final-aiot-jobs-inferência-e-assistente). |
| Demonstração com ESP32 no Wokwi | Use a [base com diagnóstico](#esp32wokwi-legado) e siga o guia do firmware. |

> O ColdSafe é um protótipo acadêmico. Ele não é um sistema médico, sanitário
> ou regulatório certificado.

## 1. Pré-requisitos

- Git, Python 3 e `curl`. Docker Desktop no macOS ou Docker Engine no Linux,
  com Docker Compose. A composição padrão foi validada com Compose v5.1.0.
- No Windows, use um terminal Linux no WSL 2 com a integração do Docker Desktop
  habilitada. Clone no sistema de arquivos da distribuição, por exemplo em
  `~/projetos`. Os scripts de segredos usam permissões de arquivo POSIX e os
  exemplos de terminal usam sintaxe Bash. [Guia do Docker para WSL 2](https://docs.docker.com/desktop/features/wsl/).
- Porta `5173` livre no host. API, MQTT e bancos ficam internos por padrão.
- Acesso à internet para o primeiro build e o download dos pesos do assistente.
  Node e as dependências da aplicação são instalados durante o build Docker.
- O simulador Python v3 da pilha final roda no Compose. VS Code, PlatformIO e
  licença Wokwi são opcionais, somente para os dois ESP32 do caminho legado.

Use a revisão da entrega que contém `compose.override.yaml`. Para instalar a
versão publicada na branch principal:

```bash
git clone --branch main https://github.com/VitorFcosta/ColdSafe.git
cd ColdSafe
```

Confirme o ambiente e identifique a versão usada no ensaio:

```bash
git rev-parse --short HEAD
git status --short
python3 --version
docker compose version
docker info
```

Confira se `compose.yaml` e `compose.override.yaml` existem na raiz. A presença
do segundo arquivo habilita a composição completa no comando padrão.
`docker info` confirma que o daemon está iniciado. As versões fixadas estão em
[`version-matrix.md`](version-matrix.md).

## 2. Criar a configuração local

Gere somente os segredos ausentes, preservando configuração já existente:

```bash
python3 scripts/generate-secrets.py
```

O script cria `.env` a partir do exemplo quando necessário e preenche campos
vazios/ausentes: JWT, PostgreSQL, MQTT, administração inicial do InfluxDB e as
onze identidades RabbitMQ. Gera valores distintos com 32 bytes aleatórios e
grava atomicamente com permissão `0600`, sem imprimir segredos. Valores existentes
não são rotacionados; uma segunda execução conserva o conteúdo. O usuário inicial
do InfluxDB recebe `coldsafe-admin` somente se estiver vazio/ausente.
Revise configurações não secretas antes da primeira subida. O script exige
arquivo UTF-8 com uma atribuição por linha, recusa duplicatas/links simbólicos e
deve ser executado uma instância de cada vez. `.env` continua ignorado pelo Git.

Deixe `INFLUXDB_TOKEN` vazio por enquanto. O Compose exige um valor mesmo
quando somente o InfluxDB é iniciado, então a próxima seção usa um marcador
temporário apenas no ambiente dos comandos de bootstrap. Ele não é salvo no
`.env`, não é usado pelo InfluxDB e não inicia o backend. O token administrativo
`DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` nunca deve ser usado como `INFLUXDB_TOKEN`.

Se também usar ESP32/Wokwi, copie `firmware/include/secrets.example.h` para
`firmware/include/secrets.h` somente se ausente e configure as duas senhas
conforme [`firmware/README.md`](../firmware/README.md). Preserve a configuração
local existente. A pilha Python v3 dispensa esse arquivo. Mais detalhes estão em
[`configuration.md`](configuration.md).

## 3. Inicializar o InfluxDB e provisionar tokens restritos

Antes de subir a aplicação completa, inicie **somente** o InfluxDB:

```bash
INFLUXDB_TOKEN=bootstrap-not-used docker compose -f compose.yaml config --quiet
INFLUXDB_TOKEN=bootstrap-not-used docker compose -f compose.yaml up -d --wait --wait-timeout 180 influxdb
INFLUXDB_TOKEN=bootstrap-not-used docker compose -f compose.yaml ps influxdb
python3 scripts/bootstrap-influx.py
```

Em uma instalação nova, o container cria organização e bucket legado do `.env`.
Execute com o serviço `healthy`; o script cria `telemetry_live` com retenção de **168h**
se ausente, provisiona as duas autorizações restritas e salva somente campos vazios
do `.env` atomicamente com permissão `0600`. Nenhum token é mostrado na saída.
As autorizações são separadas:

- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`: reservado à administração local;
- `INFLUXDB_TOKEN`: leitura e escrita somente no bucket legado configurado;
- `INFLUXDB_WRITER_TOKEN`: somente escrita em `telemetry_live`.

Reexecutar valida bucket, retenção, organização, status e permissões, conserva
tokens existentes e recupera uma autorização criada antes de falha na gravação
local. Tokens inválidos, amplos ou inativos causam erro; o script não os rotaciona,
não muda retenção existente e não apaga dados. Execute uma instância por vez, sem
editar o `.env` durante o bootstrap. O token admin é expandido somente dentro do
container e o JSON da CLI é capturado, sem entrar na saída ou nos argumentos do host.
Para outra composição, use `--env-file`, `--project-name` e um `--compose-file` por
arquivo, na mesma ordem da subida. O script ignora overrides do shell para as chaves
presentes no arquivo; mantenha o mesmo arquivo como fonte da composição.

As variáveis `DOCKER_INFLUXDB_INIT_*` só inicializam um volume vazio. Em um
volume existente, alterar esses valores não recria usuário, organização,
bucket ou token.

Flags conferidas na documentação oficial de
[autorizações](https://docs.influxdata.com/influxdb/v2/reference/cli/influx/auth/create/)
e [buckets](https://docs.influxdata.com/influxdb/v2/reference/cli/influx/bucket/create/).

### Opcional — identificar a origem das imagens

Antes das construções nas próximas seções, ative os metadados Git nativos do
Docker Buildx no terminal atual. No macOS/Linux:

```bash
export BUILDX_GIT_LABELS=full
export BUILDX_GIT_CHECK_DIRTY=1
```

No Windows PowerShell:

```powershell
$env:BUILDX_GIT_LABELS = "full"
$env:BUILDX_GIT_CHECK_DIRTY = "1"
```

Continue usando os mesmos comandos Compose deste runbook. As variáveis valem
para os builds iniciados nesse terminal e não alteram o ambiente dos serviços.
O rótulo `org.opencontainers.image.revision` informa o commit; o sufixo `-dirty`
indica alterações locais não commitadas. Esse rótulo é uma indicação de origem,
não uma assinatura nem um hash de todos os arquivos locais. Sem essas variáveis,
outros comandos de construção podem produzir imagens sem os rótulos do projeto.

Confira uma imagem construída:

```bash
docker image inspect coldsafe-backend --format '{{json .Config.Labels}}'
```

As imagens Python copiam os módulos de execução, schemas e migrações SQL
necessárias; testes e documentação continuam no checkout. Para verificar as
nove imagens da pilha completa, depois de construí-las, execute:

```bash
COLDSAFE_IMAGE_TESTS=1 python3 -m unittest discover -s backend/tests/infra -p test_application_images.py -v
```

No PowerShell, defina `$env:COLDSAFE_IMAGE_TESTS = "1"` e execute o mesmo comando
a partir de `python` (ou do nome disponível para Python 3). Os testes usam
containers temporários sem rede e sem volumes pessoais, importam módulos sem
iniciar servidores/jobs e os removem ao concluir. Nenhum modelo é carregado.
Sem `COLDSAFE_IMAGE_TESTS=1`, esses testes são ignorados. As etiquetas locais
`coldsafe-*` devem corresponder ao checkout testado e ao projeto Compose `coldsafe`.

Referência: [metadados Git do Buildx](https://docs.docker.com/build/building/variables/#buildx_git_labels).

## 4. Subir a base para comissionamento

Esta etapa inicial permite criar conta/ambiente/dispositivo antes de ativar o v3.
Use `-f compose.yaml` explicitamente: sem essa opção, o Compose também carrega
`compose.override.yaml` e seleciona a pilha completa, que já exige proprietário
e catálogo comissionados. O comando normal da pilha final está na seção seguinte.
Valide novamente a configuração e recrie os containers para carregar o token
restrito salvo no `.env`:

```bash
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml up -d --build --force-recreate --wait --wait-timeout 180
docker compose -f compose.yaml ps -a
```

O resultado esperado é:

- `mosquitto`, `influxdb`, `postgres`, `rabbitmq`, `backend` e `frontend` em execução e `healthy`;
- `mosquitto-init` e `rabbitmq-init` encerrados com código `0` (`Exited (0)`).
  São tarefas de inicialização, não serviços persistentes.

Na primeira inicialização, o backend aplica as migrações relacionais. O volume
`postgres-data` preserva cadastros e configurações entre reinícios; não o apague
ao atualizar a aplicação.

O `mosquitto-init` gera automaticamente o arquivo de senhas no volume
`mosquitto-auth` com os valores do `.env`. Não crie nem edite um arquivo
`passwords` manualmente.

## 5. Verificar a aplicação

Teste o processo da API, a conexão com suas dependências e a entrega do frontend:

```bash
curl -fsS http://127.0.0.1:5173/health/live
curl -fsS http://127.0.0.1:5173/health/ready
curl -fsS -o /dev/null http://127.0.0.1:5173/dashboard
```

Todos os comandos devem terminar com código `0`. `/health/live` confirma que a
API responde. `/health/ready` indica que as dependências verificadas pela API
estão acessíveis. A requisição a `/dashboard` confirma que o Nginx entrega a
página da aplicação. A consulta de dados exige login. Abra
[http://localhost:5173/](http://localhost:5173/) no navegador, crie uma conta
local e entre. Para AIoT v3, continue na seção da pilha final abaixo e cadastre
`sim-lab-01` em `/manage`. Somente para o percurso ESP32 legado, crie dois
ambientes e associe `esp32-lab-01` e `esp32-lab-02`, um a cada ambiente.
Um resumo de dispositivo
cadastrado exige sessão Bearer do proprietário: uma consulta anônima ou de
outra conta deve ser recusada. Antes de chegar telemetria, o resumo autenticado
pode representar ausência de leitura sem que a API esteja indisponível.

REST, WebSocket, `/docs`, `/redoc` e `/openapi.json` usam a mesma porta do
frontend. `/docs` carrega JS/CSS/favicon locais de `/docs-assets/`, sem CDN ou
validador remoto; `/redoc` redireciona para a mesma documentação. Acesse pela
porta do frontend: os assets são servidos pelo Nginx, não pela porta de diagnóstico
direta do backend. Downloads de dependências/pesos acontecem no preparo/build,
antes do ensaio sem rede externa. O container serve o build Vue por Nginx sem root; não executa Vite
nem monta os fontes. A documentação HTTP tem link no dashboard.

### ESP32/Wokwi legado

Habilite explicitamente a base e o diagnóstico:

```bash
docker compose -f compose.yaml -f compose.debug.yaml up -d --build --wait
```

O overlay publica API `127.0.0.1:8000`, MQTT `127.0.0.1:1883` e management RabbitMQ
`127.0.0.1:15672`, além do frontend. O build de diagnóstico inclui link para o
RabbitMQ no dashboard. Isso não concede privilégios de management às identidades
de transporte; a autorização operacional do painel pertence à B2-15.
No Wokwi, MQTT usa `host.wokwi.internal`. Para voltar à base de comissionamento,
use `docker compose -f compose.yaml up -d --build --force-recreate --wait`.
Após concluir o comissionamento, a partida normal usa `docker compose up`.
Preserve os volumes em ambas as operações.

Para validar o fluxo legado ESP32, compile os dois alvos e abra as duas simulações
seguindo [`firmware/README.md`](../firmware/README.md). Cada ESP32 usa sua
própria senha MQTT do `.env`. Confira leituras, luminosidade e alertas por
dispositivo; solicite o LED pela interface e aguarde a confirmação. Altere a
temperatura além do limite para acionar o buzzer e devolva-a à faixa de
recuperação. O passo a passo e a separação entre verificações automáticas e
manuais estão em [`testing/demo-rehearsal.md`](testing/demo-rehearsal.md).

Para testar persistência, anote um cadastro e uma leitura antes de
`docker compose -f compose.yaml down`, suba a mesma base novamente sem
`--volumes` e confirme que ambos ainda existem. Interrompa e retome Mosquitto para observar perda/retorno de telemetria;
um comando sem confirmação deve aparecer como `unconfirmed`, nunca como sucesso.

## Pilha final: AIoT, jobs, inferência e assistente

As seções 1–5 preparam a base. Para iniciar o percurso completo, comissione
primeiro a conta e o dispositivo; iniciar a pilha antes disso impede a validação
do proprietário. O bootstrap de infraestrutura não cria contas de aplicação.

1. Com a base saudável, crie uma conta local, um ambiente e o dispositivo MQTT
   **`sim-lab-01`**. Entre na conta e abra **Ambientes e dispositivos**
   (`/manage`). Crie um ambiente, como **Laboratório**, selecione-o e cadastre
   o dispositivo. Use `sim-lab-01` como ID MQTT e, por exemplo,
   **Ventilador ColdSafe** como nome visível.

   Para localizar os UUIDs, abra o [Swagger local](http://localhost:5173/docs),
   execute `POST /api/v1/auth/login` e use o `data.token` no botão **Authorize**.
   Faça as consultas abaixo e copie somente os identificadores para a configuração:

   | Campo de configuração | Onde encontrar |
   | --- | --- |
   | `GATEWAY_OWNER_USER_ID` e `WRITER_OWNER_USER_ID` | `data.user_id` de `GET /api/v1/auth/me` |
   | `environment_id` do catálogo | `id` do ambiente em `GET /api/v1/environments` |
   | `device_record_id` do catálogo | `id` do registro com `mqtt_device_id: sim-lab-01` em `GET /api/v1/environments/{environment_id}/devices` |

   Em instalação nova, o cadastro começa como `operator`. Laboratório, Treinamento
   e Mensageria exigem `admin`: obtenha esse papel do administrador da instalação
   via `PATCH /api/v1/auth/users/{user_id}/role`. O cadastro público cria
   a conta com o papel `operator`.

   **Somente no primeiro comissionamento local**, quando ainda não existe nenhum
   admin, o operador da infraestrutura pode promover explicitamente a conta que
   acabou de cadastrar. Substitua `UUID_DA_CONTA` pelo UUID conferido em `/auth/me`:

   ```sh
   docker compose -f compose.yaml exec -T postgres sh -ec \
     'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v owner_id="$1"' \
     sh UUID_DA_CONTA <<'SQL'
   UPDATE users SET role = 'admin'
   WHERE id = :'owner_id'::uuid
     AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin')
   RETURNING id, email, role;
   SQL
   ```

   Confira exatamente uma linha, com o UUID/email esperados e `role=admin`.
   Zero linhas significa conta ausente ou admin já existente: confira o cadastro
   e use a API administrativa, sem remover a proteção SQL. O parâmetro do `psql`
   evita interpolar o UUID como código. Este é um passo manual do proprietário
   da instalação, não promoção automática pelo produto. Depois, confirme o papel
   atual em `/api/v1/auth/me` e entre novamente na interface para atualizar a
   navegação. Os demais papéis passam pelo endpoint com auditoria.
2. Crie o diretório e copie o exemplo, preservando um catálogo já criado:

   ```sh
   mkdir -p simulator/local
   if [ ! -e simulator/local/catalog.json ]; then
     cp simulator/catalog.example.json simulator/local/catalog.json
   fi
   ```

   Troque `device_record_id` e `environment_id` pelos registros criados. Use
   `python3 -c 'import uuid; print(uuid.uuid4())'` para gerar um UUID distinto para
   cada equipamento, sensor e atuador novo. Preserve esses IDs nos reinícios.
   Mantenha `device_id=sim-lab-01` e os nomes das seis medições e dos dois atuadores.
   O diretório e arquivo devem ser legíveis pelo UID `65532`, sem guardar segredos.
   O [guia do simulador](../simulator/README.md#cadastro-e-execução) explica o contrato.
3. Defina **o mesmo UUID da conta proprietária** em `GATEWAY_OWNER_USER_ID` e
   `WRITER_OWNER_USER_ID` no `.env`. Preserve JWT, senhas e tokens existentes.
   Reexecute `python3 scripts/bootstrap-influx.py` para verificar as permissões
   de InfluxDB antes de ativar o writer.
4. Na raiz do checkout, valide a composição padrão:

   ```sh
   docker compose config --quiet
   docker compose config --services
   ```

   O Compose combina automaticamente `compose.yaml` e `compose.override.yaml`.
   A seleção normal tem 16 serviços: 14 persistentes e dois inicializadores.
   Não são necessários `-f`, perfis ou função de shell. Variáveis externas
   `COMPOSE_FILE`/`COMPOSE_PROFILES` podem alterar essa seleção; não as configure
   para reproduzir a partida padrão. Para `--project-name`/`--env-file` próprios,
   mantenha-os em todas as operações. Não publique
   `docker compose config` sem `--quiet`: a configuração resolvida contém segredos.
5. Prepare os pesos uma vez, com `llm` e `ollama` parados. Se esses serviços
   já estiverem em execução, aguarde os jobs ativos terminarem e use
   `docker compose stop llm ollama` antes dos comandos abaixo. O preparo exige
   internet e escreve no volume dos modelos. O runtime usa a rede interna.

   ```sh
   docker compose --profile llm-setup run --rm --no-deps ollama-prepare
   docker compose up -d --build --wait --wait-timeout 420
   docker compose ps -a
   ```

   Esperado: bancos, brokers, API, frontend, simulador, gateway, writer,
   geração, treino, inferência (`models`), `ollama` e coordenador `llm` saudáveis;
   inicializadores com `Exited (0)`. O `ollama-prepare` termina após baixar
   `llama3.2:3b-instruct-q4_K_M`; ele não é um serviço contínuo. Estar saudável
   não significa que uma previsão já possui uma hora de histórico nem que um
   modelo de inferência foi treinado/ativado.
6. Confira os sinais de funcionamento pela porta `5173`:

   ```sh
   curl -fsS http://127.0.0.1:5173/health/live
   curl -fsS http://127.0.0.1:5173/health/ready
   ```

   | O que conferir | Resultado esperado |
   | --- | --- |
   | `/health/live` e `/health/ready` | HTTP 200 nos dois endpoints. |
   | **Monitoramento → Visão geral**, na conta proprietária | `sim-lab-01` mostra as seis medições, com o horário avançando. Ao testar o LED, confira o ACK e depois o estado observado na leitura. |
   | **Saúde e previsões** | Uma instalação nova pode mostrar ausência de modelo ou histórico insuficiente. A previsão exige um pacote ativo e uma hora de histórico causal com a configuração padrão. |
   | **Assistente** | A tela e `/api/v3/llm/status` indicam o estado do modelo para uma sessão válida. Aguarde a disponibilidade antes de perguntar. |

   Na conta admin, confira também filas em `/messaging`, geração em
   `/laboratory` e treino em `/training`. Jobs precisam
   chegar ao estado final persistido; uma resposta HTTP `202` é só aceite.
   Durante geração/treino, o assistente deve pausar e voltar após o cálculo.
   Monitore `docker compose stats --no-stream` e confira `.State.OOMKilled` por container
   (`docker inspect ...`); saúde isolada não comprova ausência de OOM.

A capacidade medida e os limites estão nos ensaios [B2-33](evidence/b2-33.json)
e [B2-34](evidence/b2-34.json). A rodada B2-34/R4 passou com o Mac conectado à
tomada (AC/60 W), sem OOM nas amostras; o treino ficou próximo de 1 GiB e as
quatro respostas SSE levaram 35–67 s. Falhas anteriores foram preservadas, sem
atribuir causalidade exclusiva à bateria. Use a máquina ligada à tomada e sem
concorrência de testes pesados no ensaio. A B2-36 ajusta o prazo de pré-carga
para 300 s e usa 420 s na preparação da pilha; geração de respostas permanece
limitada a 90 s. O heartbeat/start_period do coordenador usa 360 s: cobre
pré-carga de 300 s após descarga normal rápida, sem garantir o pior caso teórico
de descarga de 180 s seguida de carga de 300 s. Disponibilidade do modelo deve
ser conferida em `/api/v3/llm/status`, além da saúde dos containers.
Os limites do Compose não constituem medição de consumo. Para reproduzir o
ensaio automatizado, use a pilha descartável descrita na evidência B2-34, sem apontar o
teste para volumes/credenciais pessoais.

### Reinício e recuperação preservando dados

Use os mesmos comandos `docker compose` também para recuperação. Antes de manutenção,
anote conta/ambiente, um ID de evento persistido, um job concluído e o modelo
ativo. Faça backup conforme o [guia de migrações](../backend/migrations/README.md).
O volume `gateway-state` guarda o diário de borda; `job-artifacts` e
`training-artifacts` guardam datasets e pacotes; `ollama-data` guarda pesos.

```sh
docker compose down
docker compose up -d --wait --wait-timeout 420
docker compose ps -a
```

Confirme os mesmos cadastros, eventos, jobs e pacotes após a subida. Não execute
`down --volumes`, não apague filas, não recrie credenciais como correção e não
edite status de jobs para liberar a memória. O estado físico/desgaste do simulador
reinicia; o histórico persistido continua no banco.

- **MQTT/RabbitMQ:** pare/retome apenas um broker por vez (`docker compose stop mosquitto`
  e `docker compose start mosquitto`, ou `rabbitmq`). Observe freshness e reconexão.
  Eventos já persistidos devem continuar consultáveis; ausência de publicação
  durante interrupção do simulador não é recuperada como dado histórico inventado.
- **Writer:** use o ensaio de backlog da seção de Mensageria abaixo. Para/retoma
  deve reduzir mensagens pendentes e produzir recibos `telemetry_persisted`.
- **Geração/treino/inferência:** use `stop`/`start` do serviço correspondente
  (`generation`, `training` ou `models`) e consulte o mesmo job/pedido. Preserve
  IDs, outbox, AMQP e arquivos. Tentativas esgotadas/DLQ exigem recuperar a mensagem
  original; não publique um novo pedido para disfarçar falha. Não reinicie
  PostgreSQL durante cálculo real: sua sessão sustenta a exclusão mútua.
- **Ollama/coordenador:** indisponibilidade pausa o assistente, conservando o
  monitoramento. Para recuperação normal, `docker compose start ollama llm` e confira
  status autenticado em `/api/v3/llm/status`. Se houver marcador de carga ambígua,
  pare `llm`, reinicie `ollama` e somente depois remova o marcador operacional:

  ```sh
  docker compose stop llm
  docker compose restart ollama
  docker compose exec -T postgres sh -ec \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM llm_memory_guard WHERE id = 1;"'
  docker compose start llm
  ```

  Não limpe a trava com um carregador ainda vivo. `/api/ps` vazio sozinho não
  prova ausência de carga em curso. O procedimento remove uma trava, preservando
  jobs, pesos e modelos ativos; ver [coordenação de memória](configuration.md#ollama-local-e-memória-b2-30).

## 6. Diagnóstico

Para inspecionar a base durante o comissionamento, use `docker compose -f compose.yaml`.
Os exemplos desta seção usam a pilha completa. Para incluir as portas locais de
diagnóstico, liste os arquivos explicitamente, na ordem:

```sh
docker compose -f compose.yaml -f compose.override.yaml -f compose.debug.yaml up -d --build --wait --wait-timeout 420
```

Confira o [roteiro do InfluxDB](aiot/presentation.md#ensaio-do-passo-6--10112026)
para abrir também o Data Explorer. Sem overlays de diagnóstico, só a porta
`127.0.0.1:5173` é publicada.

### Mensageria B2-16: parar e retomar o gravador

Pré-condições: catálogo comissionado, gateway/simulador/writer funcionando,
token exclusivo do writer e Mensageria habilitada conforme
[configuração](configuration.md#amostras-privadas-b2-16). A ativação somente de
`compose.messaging.yaml` não inicia produtores nem o gravador.
Use `docker compose` na raiz do checkout, com o comissionamento concluído.
Mantenha o mesmo projeto e arquivo de ambiente durante toda a falha controlada.

1. Entre como admin proprietário do ambiente e abra `/messaging`. Anote
   `coldsafe.writer`, horário da coleta e IDs das últimas mensagens.
2. Pare **somente o gravador**, mantendo o produtor em execução por alguns segundos:

   ```sh
   docker compose stop writer
   docker compose ps -a writer
   docker compose exec rabbitmq rabbitmqctl -q list_queues -p coldsafe name messages_ready messages_unacknowledged
   ```

3. Confira aumento de mensagens prontas no writer e novos resumos na página.
   A amostragem do broker e o polling introduzem atraso. `consumers=0` não prova
   parada: o gravador usa polling e pode mostrar zero enquanto funciona.
4. Retome o mesmo serviço, sem apagar fila ou volume:

   ```sh
   docker compose start writer
   docker compose logs --tail 30 writer
   ```

5. Confira redução do backlog e recibos `telemetry_persisted`. Para observar zero
   estável, pare brevemente o simulador (`docker compose stop simulator`)
   e retome-o depois (`docker compose start simulator`).
   Fila vazia isoladamente não comprova persistência; o ensaio automatizado abaixo
   confere cada ID e as seis medições no InfluxDB.

A UI não controla Docker nem confirma, elimina ou reenvia mensagens da DLQ.
Os resumos exibem fila de origem, motivo do broker e erro de validação quando
identificável. `rejected` por si só não revela a causa da aplicação. Mensagem sem
identidade privada verificável fica fora da amostra, embora o original continue
na DLQ e contribua para o contador global. Ausência de novos resumos por 30 s
indica amostra sem atualização, não diagnóstico automático de serviço parado.

Para injetar erro com segurança e verificar integridade/recuperação, use a pilha
**descartável** do teste; não publique dados inválidos na instalação pessoal:

```sh
COLDSAFE_WRITER_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_observation_integration.py -q -s --no-cov -o addopts=''
```

Requer Docker, Python/lock de desenvolvimento, Node/lock do frontend e Chromium
preparados conforme [frontend](../frontend/README.md#como-executar).
`COLDSAFE_NODE_BINARY` e `COLDSAFE_FRONTEND_NODE_MODULES` permitem indicar
instalações temporárias com as mesmas versões. O teste para/retoma seu próprio
writer, injeta medição inválida, verifica a DLQ sem confirmar o original e compara
persistência antes/depois, além de conferir a página pelo navegador.

### Porta já está em uso

O Docker informa qual publicação falhou. Verifique primeiro se outro container
ocupa as portas do ColdSafe:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

No macOS, localize processos do host com:

```bash
lsof -nP -iTCP:1883 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

No Linux, use:

```bash
ss -ltnp | grep -E ':(1883|8000|5173)([[:space:]]|$)'
```

Encerre ou reconfigure o processo conflitante e execute novamente
`docker compose up -d --build`. Alterar as portas do Compose também exige
ajustar os endereços usados pelo firmware, frontend e testes manuais.

### Serviço `unhealthy`, reiniciando ou parado

Veja o estado completo e os últimos logs sem imprimir o conteúdo do `.env`:

```bash
docker compose ps -a
docker compose logs --tail=100 mosquitto
docker compose logs --tail=100 influxdb
docker compose logs --tail=100 postgres
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
```

Para inspecionar o resultado do healthcheck de um serviço específico, por
exemplo o backend:

```bash
docker inspect "$(docker compose ps -q backend)" \
  --format '{{json .State.Health}}'
```

Erros comuns:

- `Resource deadlock would occur` ou `edeadlk` ao ler configuração dos brokers:
  a versão anterior montava arquivos do host durante a execução. As imagens
  atuais incluem configuração e ACL no build. Execute
  `docker compose up -d --build --wait --wait-timeout 180` para aplicar a correção,
  preservando os volumes e o `.env`. Reconstrua também após editar arquivos em
  `infra/mosquitto` ou `infra/rabbitmq`. Não apague volumes para corrigir esse erro.
- `mosquitto-init` falha: confirme que as três senhas MQTT estão preenchidas no
  `.env`; depois recrie o inicializador e o broker com
  `docker compose up -d --force-recreate mosquitto-init mosquitto`.
- `backend` não fica pronto: confirme que `INFLUXDB_TOKEN` é o token restrito
  criado na seção 3, e não o token administrativo; confirme também que
  `postgres` está saudável e que `POSTGRES_PASSWORD` corresponde à senha
  usada na criação do volume;
  então rode `docker compose up -d --no-deps --force-recreate backend`.
- autenticação administrativa do InfluxDB falha em um volume antigo: use as
  credenciais que inicializaram esse volume. Alterar o `.env` não altera o
  estado já persistido. O mesmo vale para as credenciais do PostgreSQL.
  Não apague volumes com histórico sem decidir e fazer o
  backup necessário.
- frontend abre, mas não acessa a API: verifique `/health/ready` pela porta
  `5173` e os logs de `frontend`/`backend`. O build Docker usa URLs relativas;
  variáveis Vite no ambiente do container não alteram uma build já pronta.
- `gateway`, `writer` ou `models` reiniciam após um checkout novo: verifique
  se o catálogo montado é legível e se o registro do dispositivo, o ambiente e
  os UUIDs de proprietário correspondem ao cadastro no PostgreSQL atual.
  Retome o [comissionamento](#pilha-final-aiot-jobs-inferência-e-assistente)
  antes de tentar subir a pilha novamente.
- Ollama não encontra os pesos: confirme que `ollama-prepare` concluiu usando
  o mesmo projeto Compose e volume da pilha final. Use o preparo da seção
  [Pilha final](#pilha-final-aiot-jobs-inferência-e-assistente).

### Dependências do frontend desatualizadas

Depois de alterar fontes, `package.json` ou lock, reconstrua a imagem estática:

```bash
docker compose up -d --build --no-deps --force-recreate --wait frontend
```

O runtime frontend não tem npm ou volume de dependências. Reconstruir sua imagem
preserva os volumes dos bancos e brokers. A porta do frontend continua `5173`.

## 7. Encerrar sem apagar dados

Pare e remova os containers e redes da composição:

```bash
docker compose down
```

Esse comando preserva os volumes nomeados, incluindo o histórico do InfluxDB, os
cadastros do PostgreSQL e
as credenciais geradas do Mosquitto. Não use `docker compose down --volumes` no
fluxo normal: `--volumes` apaga esses dados e força um novo bootstrap.
