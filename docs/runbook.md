# Runbook local do ColdSafe

Este é o caminho canônico para preparar, iniciar, verificar e encerrar o
ColdSafe em outro computador. Execute todos os comandos a partir da raiz do
repositório.

> O ColdSafe é um protótipo acadêmico. Ele não é um sistema médico, sanitário
> ou regulatório certificado.

## 1. Pré-requisitos

- Git para obter o repositório.
- Docker Desktop no macOS ou Docker Engine no Linux, com Docker Compose v2.
- Portas `1883`, `8000` e `5173` livres no host.
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

Copie os exemplos versionados:

```bash
cp .env.example .env
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

Edite o `.env` e defina valores locais, fortes e diferentes para:

- `MQTT_BACKEND_PASSWORD`;
- `MQTT_DEVICE_PASSWORD`;
- `DOCKER_INFLUXDB_INIT_USERNAME`;
- `DOCKER_INFLUXDB_INIT_PASSWORD`;
- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`.

Use um gerenciador de senhas ou outro gerador seguro. Não coloque os valores
no histórico do terminal, não altere `.env.example` e não envie o `.env` para o
Git. As credenciais de inicialização do InfluxDB são administrativas e devem
ser exclusivas deste ambiente local.

Deixe `INFLUXDB_TOKEN` vazio por enquanto. O Compose exige um valor mesmo
quando somente o InfluxDB é iniciado, então a próxima seção usa um marcador
temporário apenas no ambiente dos comandos de bootstrap. Ele não é salvo no
`.env`, não é usado pelo InfluxDB e não inicia o backend. O token administrativo
`DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` nunca deve ser usado como `INFLUXDB_TOKEN`.

Depois, edite `firmware/include/secrets.h` e substitua somente
`REPLACE_WITH_MQTT_DEVICE_PASSWORD` pelo mesmo valor definido em
`MQTT_DEVICE_PASSWORD`. Preserve o usuário `coldsafe-device`, o tópico e os
demais valores do exemplo. Mais detalhes estão em
[`configuration.md`](configuration.md).

## 3. Inicializar o InfluxDB e criar o token do backend

Antes de subir a aplicação completa, inicie **somente** o InfluxDB:

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

## 4. Subir os quatro serviços

Valide novamente a configuração e recrie os containers para carregar o token
restrito salvo no `.env`:

```bash
docker compose config --quiet
docker compose up -d --build --force-recreate --wait --wait-timeout 180
docker compose ps -a
```

O resultado esperado é:

- `mosquitto`, `influxdb`, `backend` e `frontend` em execução e `healthy`;
- `mosquitto-init` encerrado com código `0` (`Exited (0)`). Ele é uma tarefa de
  inicialização, não um quinto serviço persistente.

O `mosquitto-init` gera automaticamente o arquivo de senhas no volume
`mosquitto-auth` com os valores do `.env`. Não crie nem edite um arquivo
`passwords` manualmente.

## 5. Verificar a aplicação

Teste liveness, readiness, API e frontend:

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsS http://127.0.0.1:8000/api/v1/monitoring/summary
curl -fsS -o /dev/null http://127.0.0.1:5173/
```

Todos os comandos devem terminar com código `0`. Antes de chegar telemetria, o
resumo pode representar ausência de leitura; isso não significa que a API está
indisponível. Abra [http://localhost:5173](http://localhost:5173) no navegador
e confirme que o dashboard é carregado.

Para validar o fluxo completo, execute a simulação seguindo
[`firmware/README.md`](../firmware/README.md). Depois da primeira publicação do
ESP32, confirme novamente o dashboard e o resumo da API. O firmware precisa
usar a mesma `MQTT_DEVICE_PASSWORD` do `.env`.

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

- `mosquitto-init` falha: confirme que as duas senhas MQTT estão preenchidas no
  `.env`; depois recrie o inicializador e o broker com
  `docker compose up -d --force-recreate mosquitto-init mosquitto`.
- `backend` não fica pronto: confirme que `INFLUXDB_TOKEN` é o token restrito
  criado na seção 3, e não o token administrativo;
  então rode `docker compose up -d --no-deps --force-recreate backend`.
- autenticação administrativa do InfluxDB falha em um volume antigo: use as
  credenciais que inicializaram esse volume. Alterar o `.env` não altera o
  estado já persistido. Não apague volumes com histórico sem decidir e fazer o
  backup necessário.
- frontend abre, mas não acessa a API: verifique se readiness retorna `200`, se
  `http://localhost:8000` corresponde a `VITE_API_BASE_URL` e se
  `http://localhost:5173` está permitido em `CORS_ORIGINS`.

### Dependências do frontend desatualizadas

Se os logs do frontend mostrarem módulos ausentes depois de uma alteração em
`package.json` ou `package-lock.json`, atualize somente o volume de dependências
do frontend e recrie esse serviço:

```bash
docker compose stop frontend
docker compose run --rm --no-deps frontend npm ci
docker compose up -d --no-deps --force-recreate --wait frontend
```

Essa sequência não apaga nem recria os volumes de dados do InfluxDB ou do
Mosquitto. Ela foi validada com o frontend saudável e acessível na porta `5173`.

## 7. Encerrar sem apagar dados

Pare e remova os containers e redes da composição:

```bash
docker compose down
```

Esse comando preserva os volumes nomeados, incluindo o histórico do InfluxDB e
as credenciais geradas do Mosquitto. Não use `docker compose down --volumes` no
fluxo normal: `--volumes` apaga esses dados e força um novo bootstrap.
