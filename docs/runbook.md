# Runbook local do ColdSafe

Este é o caminho canônico para preparar, iniciar, verificar e encerrar o
ColdSafe em outro computador. Execute todos os comandos a partir da raiz do
repositório.

> O ColdSafe é um protótipo acadêmico. Ele não é um sistema médico, sanitário
> ou regulatório certificado.

## 1. Pré-requisitos

- Git para obter o repositório.
- Docker Desktop no macOS ou Docker Engine no Linux, com Docker Compose v2.
- Porta `5173` livre no host. API, MQTT e bancos ficam internos por padrão.
- Para simular o dispositivo: VS Code, PlatformIO IDE, Wokwi Simulator e uma
  licença Wokwi válida. Esse passo é opcional para verificar apenas a aplicação.

Confirme o ambiente:

```bash
docker --version
docker compose version
docker info
```

O último comando também confirma que o daemon do Docker está iniciado. As
versões fixadas das imagens e dos runtimes estão em
[`version-matrix.md`](version-matrix.md).

## 2. Criar a configuração local

Gere somente os segredos ausentes, preservando configuração já existente:

```bash
python3 scripts/generate-secrets.py
test -e firmware/include/secrets.h || cp firmware/include/secrets.example.h firmware/include/secrets.h
```

O script cria `.env` a partir do exemplo quando necessário e preenche campos
vazios/ausentes: JWT, PostgreSQL, MQTT, administração inicial do InfluxDB e as
dez identidades RabbitMQ. Gera valores distintos com 32 bytes aleatórios e
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

Depois, edite `firmware/include/secrets.h` e configure as senhas dos dois
dispositivos conforme [`firmware/README.md`](../firmware/README.md). Preserve
as configurações locais existentes. Mais detalhes estão em
[`configuration.md`](configuration.md).

## 3. Inicializar o InfluxDB e criar o token do backend

Antes de subir a aplicação completa, inicie **somente** o InfluxDB:

Se `INFLUXDB_TOKEN` já contém a autorização restrita válida do volume existente,
vá à seção 4; não crie nem substitua tokens sem necessidade.

```bash
INFLUXDB_TOKEN=bootstrap-not-used docker compose config --quiet
INFLUXDB_TOKEN=bootstrap-not-used docker compose up -d influxdb
INFLUXDB_TOKEN=bootstrap-not-used docker compose ps influxdb
```

Aguarde até o estado do serviço aparecer como `healthy`. Em uma instalação
nova, o container cria a organização e o bucket configurados no `.env`.

Crie então uma autorização com leitura e escrita somente no bucket de
telemetria:

```bash
INFLUXDB_TOKEN=bootstrap-not-used docker compose exec influxdb sh -ec '
bucket_id="$(
  influx bucket list \
    --host http://127.0.0.1:8086 \
    --org "$DOCKER_INFLUXDB_INIT_ORG" \
    --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
    --name "$DOCKER_INFLUXDB_INIT_BUCKET" \
    --hide-headers |
  awk "NR == 1 { print \$1 }"
)"
test -n "$bucket_id"
influx auth create \
  --host http://127.0.0.1:8086 \
  --org "$DOCKER_INFLUXDB_INIT_ORG" \
  --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
  --description coldsafe-backend-telemetry \
  --read-bucket "$bucket_id" \
  --write-bucket "$bucket_id"
'
```

O comando usa o token administrativo dentro do container, sem incluí-lo na
linha de comando do host, e mostra a nova autorização. Copie o valor da coluna
`Token` para `INFLUXDB_TOKEN` no `.env`. Não copie o token administrativo e não
publique o token novo em documentação, mensagens, capturas de tela ou commits.

Ao terminar, o `.env` deve conter dois tokens diferentes:

- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`: reservado à administração local;
- `INFLUXDB_TOKEN`: leitura e escrita somente no bucket `telemetry`.

As variáveis `DOCKER_INFLUXDB_INIT_*` só inicializam um volume vazio. Em um
volume existente, alterar esses valores não recria usuário, organização,
bucket ou token.

## 4. Subir os serviços

Valide novamente a configuração e recrie os containers para carregar o token
restrito salvo no `.env`:

```bash
docker compose config --quiet
docker compose up -d --build --force-recreate --wait --wait-timeout 180
docker compose ps -a
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

Teste liveness, readiness e frontend:

```bash
curl -fsS http://127.0.0.1:5173/health/live
curl -fsS http://127.0.0.1:5173/health/ready
curl -fsS -o /dev/null http://127.0.0.1:5173/dashboard
```

Todos os comandos devem terminar com código `0`. Abra
[http://localhost:5173/](http://localhost:5173/) no navegador, crie uma conta
local e entre. No dashboard, crie dois ambientes e associe
`esp32-lab-01` e `esp32-lab-02`, um a cada ambiente. Um resumo de dispositivo
cadastrado exige sessão Bearer do proprietário: uma consulta anônima ou de
outra conta deve ser recusada. Antes de chegar telemetria, o resumo autenticado
pode representar ausência de leitura sem que a API esteja indisponível.

REST, WebSocket, `/docs`, `/redoc` e `/openapi.json` usam a mesma porta do
frontend. O container serve o build Vue por Nginx sem root; não executa Vite
nem monta os fontes. A documentação HTTP tem link no dashboard.

Para Wokwi ou diagnóstico opcional, habilite explicitamente o override:

```bash
docker compose -f compose.yaml -f compose.debug.yaml up -d --build --wait
```

Ele publica API `127.0.0.1:8000`, MQTT `127.0.0.1:1883` e management RabbitMQ
`127.0.0.1:15672`, além do frontend. O build de diagnóstico inclui link para o
RabbitMQ no dashboard. Isso não concede privilégios de management às identidades
de transporte; a autorização operacional do painel pertence à B2-15.
No Wokwi, MQTT usa `host.wokwi.internal`. Ao voltar ao modo normal, recrie com
`docker compose up -d --build --force-recreate --wait`, sem apagar volumes.

Para validar o fluxo completo, compile os dois alvos e abra as duas simulações
seguindo [`firmware/README.md`](../firmware/README.md). Cada ESP32 usa sua
própria senha MQTT do `.env`. Confira leituras, luminosidade e alertas por
dispositivo; solicite o LED pela interface e aguarde a confirmação. Altere a
temperatura além do limite para acionar o buzzer e devolva-a à faixa de
recuperação. O passo a passo e a separação entre verificações automáticas e
manuais estão em [`testing/demo-rehearsal.md`](testing/demo-rehearsal.md).

Para testar persistência, anote um cadastro e uma leitura antes de
`docker compose down`, suba novamente sem `--volumes` e confirme que ambos ainda
existem. Interrompa e retome Mosquitto para observar perda/retorno de telemetria;
um comando sem confirmação deve aparecer como `unconfirmed`, nunca como sucesso.

## 6. Diagnóstico

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
