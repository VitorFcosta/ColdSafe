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

A B2-07 exige também as dez senhas `RABBITMQ_*_PASSWORD` listadas em
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

## API AIoT opcional B2-13

Depois de preparar catálogo, proprietário, brokers e token exclusivo do writer,
habilite a API com o overlay explícito:

```sh
docker compose -f compose.yaml -f compose.aiot.yaml --profile aiot --profile simulator config --quiet
docker compose -f compose.yaml -f compose.aiot.yaml --profile aiot --profile simulator up -d --build frontend backend gateway writer simulator
```

O overlay define `AIOT_ENABLED=true`, `AIOT_CATALOG_PATH=/catalog/catalog.json`,
`AIOT_OWNER_USER_ID` a partir de `GATEWAY_OWNER_USER_ID`, e injeta somente as
senhas AMQP `commands`/`delivery` no backend. Monte o mesmo catálogo privado do
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
