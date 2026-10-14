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
são registrados localmente, sem API/tabelas. A futura validação do gateway não
pode confiar na propriedade apenas por esses IDs.
A B2-10 usa também `MQTT_GATEWAY_PASSWORD` para a conta `coldsafe-gateway`,
com publicação apenas dos comandos v3 do simulador e leitura de seus ACKs e
telemetria. O gerador cria a senha quando ausente, sem rotacionar valores.
É uma credencial distinta de `RABBITMQ_GATEWAY_PASSWORD`; o serviço de tradução
MQTT/AMQP pertence à B2-11. Campos vazios não provisionam a nova conta.
Preparação, permissões, ritmo de simulação e comandos do operador estão em
[`simulator/README.md`](../simulator/README.md). Nenhum segredo pessoal foi
alterado na execução B2-09; integração usa credenciais descartáveis.

## Permissões do token InfluxDB

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
