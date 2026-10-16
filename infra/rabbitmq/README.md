# RabbitMQ — infraestrutura B2-07

O Compose prepara o broker interno `rabbitmq:5672`, vhost `coldsafe`, com
RabbitMQ `4.3.6-management-alpine`. Não publica AMQP nem management no host.
O backend v1/v2 continua no MQTT. O [gateway B2-11](../../gateway/README.md) já
consome comandos e produz telemetria/ACK/erros; o [gravador B2-12](../../writer/README.md)
consome `coldsafe.writer`, grava InfluxDB, publica recibo e só então confirma.
A API B2-13 consome `commands`/`delivery`, com transações e entrega privada.
Demais consumidores v3 continuam posteriores.
Estas filas prontas não provam os consumidores de negócio.

## Preparação e segredos

Preencha as onze variáveis `RABBITMQ_*_PASSWORD` de `.env.example` no `.env`
privado: senhas aleatórias distintas, com pelo menos 32 caracteres. O inicializador
offline recusa valores ausentes, curtos, repetidos ou `REPLACE_WITH_...`.
Nenhuma credencial pessoal é alterada pelos testes. O broker não recebe as senhas
em seu ambiente; recebe hashes SHA-256 com salt aleatório num volume privado.
As identidades não possuem tags administrativas; não existe `guest` no volume novo.
A identidade `coldsafe-monitor` da B2-15 tem somente a tag `management`, para
inspecionar métricas no vhost autorizado; configure/read/write permanecem `^$`.
Ela não consome nem publica mensagens, não altera filas e não administra usuários.
As outras dez identidades continuam sem tags.

```bash
docker compose config --quiet
docker compose up -d --build --wait rabbitmq
docker compose exec rabbitmq rabbitmqctl -q list_users
docker compose exec rabbitmq rabbitmqctl -q list_queues -p coldsafe name messages consumers
```

O primeiro comando também exige as variáveis dos demais serviços do Compose.
`rabbitmq-init` gera `definitions.json` atomicamente e entrega diretório `0750`
e arquivo `0440` ao UID/GID `100:101` da imagem fixada. Somente esse volume é
montado como leitura pelo broker. `rabbitmq-data` mantém as mensagens; hostname
fixo mantém a identidade do nó entre recriações. Não apagar volumes para reiniciar.
Imports não removem usuários/recursos preexistentes: usar apenas o volume próprio
deste Compose. Rotação de credenciais ou remoção de identidades exige operação
administrativa explícita, conferência no broker e atualização dos consumidores.

## Filas e acesso

`bootstrap.py` é a fonte executável de nomes, bindings, permissões e políticas.
Exchange principal: topic durável `coldsafe.events`; routing keys seguem o
[contrato v3](../../contracts/aiot.md), com UUID em um único segmento.
Todos os recursos usam vhost `coldsafe`. Nenhum serviço pode declarar, alterar
ou apagar recursos; lê apenas sua fila e publica apenas seus tipos permitidos.
Publicação direta pela exchange padrão e escrita na DLX são proibidas.

| Identidade `coldsafe-…` | Fila | Tipos recebidos | Tipos publicáveis |
| --- | --- | --- | --- |
| gateway | `coldsafe.gateway` | command | telemetry, ack, processing_error |
| writer | `coldsafe.writer` | telemetry | telemetry_persisted, processing_error |
| inference | `coldsafe.inference` | telemetry, model_activation | prediction, model_status, processing_error |
| delivery | `coldsafe.delivery` | telemetry, telemetry_persisted, ack, prediction, command_status, alert, freshness, job_progress, model_status, processing_error | processing_error |
| commands | `coldsafe.commands` | telemetry, telemetry_persisted, ack, prediction, freshness | command, command_status, alert, freshness, processing_error |
| generation | `coldsafe.generation` | job_requested com header generation | job_progress, processing_error |
| training | `coldsafe.training` | job_requested com header training | job_progress, model_status, processing_error |
| observability | `coldsafe.observability` | `v3.#` e cópias da DLX/jobs.unrouted | nenhum |
| api | nenhuma | nenhum | command, job_requested, model_activation, processing_error |
| audit | `coldsafe.dlq` | originais privados com falha | nenhum |
| monitor | nenhuma | métricas via HTTP, sem corpos de mensagens | nenhum |

A observabilidade consome sua cópia; não tira mensagens das filas de negócio e
não acessa a DLQ. `audit` é uma identidade de transporte reservada à auditoria,
sem conceder acesso a usuários HTTP. A API autoriza cada consulta
antes de revelar qualquer dado. O broker limita serviços/tipos, não propriedade
de usuário ou catálogo de dispositivos: essa validação continua no consumidor.

## Painel de métricas B2-15

A página `/messaging` consulta somente `GET /api/v3/messaging` da API ColdSafe.
O backend usa `RABBITMQ_HOST`, `RABBITMQ_MANAGEMENT_PORT` (15672) e
`RABBITMQ_MONITOR_PASSWORD` com usuário fixo `coldsafe-monitor`. O overlay
`compose.messaging.yaml` fornece esses valores sem publicar portas adicionais
nem ativar o percurso AIoT completo; `compose.aiot.yaml` também os inclui.
Preparação em [configuração](../../docs/configuration.md#mensageria-b2-15).

As nove filas têm contagem total, prontas, sem confirmação, consumidores e taxas
de publicação/entrega por segundo. São métricas agregadas de infraestrutura,
restritas a administrador ColdSafe: não representam atividade de um proprietário.
`consumers` conta assinaturas registradas no broker, não processos conectados:
gateway/writer/API atuais usam `basic_get` e podem mostrar zero em operação.
O painel não deve interpretar zero como prova de serviço parado. O harness
registra uma assinatura descartável em fila vazia para conferir também esse contador.
Essa consulta de métricas não lê mensagens, payloads, nomes de conexão ou usuários RabbitMQ.
Na B2-16, a rota separada `/api/v3/messaging/messages` usa o observador e devolve
apenas resumos privados, com autorização do proprietário atual no PostgreSQL.

O serviço limita resposta e campos consultados, com timeout de socket de 3 s e cache curto para
concentrar polling. A página atualiza a cada cinco segundos; a estatística do
broker também é amostrada, portanto não é um contador instantâneo. Taxa ausente
permanece indisponível. Falha gera 503 sanitizado; o navegador identifica a última
coleta conhecida e sua idade, sem apresentar um snapshot antigo como atual.

Em instalação existente, complete apenas a chave ausente usando o gerador e
reexecute o bootstrap/import com os mesmos volumes, seguido da recriação do
backend com o overlay. Não apague volumes nem rotacione senhas existentes.
Essa operação na pilha pessoal exige execução explícita; os testes são descartáveis.

Referências verificadas para RabbitMQ 4.3: [permissões de management](https://www.rabbitmq.com/docs/management#permissions)
e [API HTTP/limitação de colunas](https://www.rabbitmq.com/docs/http-api-reference).

Pedidos `v3.job_requested.{job_id}` passam da topic para `coldsafe.jobs`
(headers). O publicador deve copiar `data.job_type` para o header AMQP `job_type`
(`generation` ou `training`); workers devem validar igualdade antes de executar.
Não modificar a routing key nem o payload. Header ausente/desconhecido segue
pela alternate exchange `coldsafe.jobs.unrouted` até a DLQ, preservando o original;
nesse caso não há `x-death`, pois não houve rejeição por um consumidor.

## Confirmação, retry e DLQ

Publicadores devem usar `delivery_mode=2`, `message_id=event_id`,
`correlation_id`, `content_type=application/json`, publisher confirms e
`mandatory=True`; confirmação do broker não significa efeito de negócio concluído.
Consumidores usam `auto_ack=False`, prefetch 1 e ACK somente após efeito durável
e idempotente. Gateway e gravador implementam seus efeitos duráveis e erros
sanitizados; os demais pertencem aos serviços futuros. Não confirmar uma leitura para WebSocket
antes de sua persistência comprovada.

- Sucesso: `basic_ack(delivery_tag)` após concluir o efeito.
- Falha permanente: `basic_reject(delivery_tag, requeue=False)` imediatamente.
- Falha transitória: `basic_reject(delivery_tag, requeue=True)`. RabbitMQ 4.3
  incrementa `x-delivery-count`; `basic_nack(requeue=True)` não incrementa esse
  contador e não deve ser usado para falhas de processamento.
- Política: `delivery-limit=2`, até três tentativas (inicial + duas novas),
  backoff nativo de 1 s e 2 s, `delayed-retry-type=failed`. Queda de conexão com
  mensagem sem ACK também conta como falha. Não republicar o evento para zerar
  o contador; a tentativa do erro sanitizado futuro é `1 + x-delivery-count`.
- Falha permanente/excesso vai à topic `coldsafe.dlx`, binding `#`, fila quorum
  `coldsafe.dlq`. Dead lettering `at-least-once` + overflow `reject-publish`
  preserva a mensagem na origem até confirmação do destino. Corpo, identidade,
  correlação e headers originais são preservados; `x-death` registra fila,
  routing key e motivo `rejected`/`delivery_limit`.

Filas são quorum duráveis, com teto de 64 MiB por fila de trabalho, memória do
broker limitada a 512 MiB/1 CPU, watermark 256 MiB e mensagem de até 256 KiB.
Exceção: a fila de cópias `observability` tem política própria de 8 MiB,
`overflow=drop-head` e `delivery-limit=2`, sem DLX. A amostra pode perder cópias
antigas ou repetidamente interrompidas; os originais de negócio/DLQ permanecem.
Essa separação evita ciclos DLX → observador → DLX e impede que uma fila de
amostras cheia rejeite publicações de negócio. A política de retry acima continua
nas sete filas de trabalho. Confirmado na documentação RabbitMQ 4.3 de
[DLX](https://www.rabbitmq.com/docs/dlx) e [limite de fila](https://www.rabbitmq.com/docs/maxlength).
DLQ não tem TTL nem ciclo para filas de trabalho. Capacidade da pilha completa
continua na B2-33. Nó único não fornece alta disponibilidade; `at-least-once`
admite duplicatas, que o consumidor deve tratar idempotentemente.

## Reproduzir os testes

Com Python `3.13.15` e o lock de desenvolvimento instalado:

```bash
.venv/bin/python -m pytest backend/tests/infra/test_rabbitmq_bootstrap.py backend/tests/infra/test_compose_contract.py backend/tests/contract -q --no-cov -o addopts=''
COLDSAFE_RABBITMQ_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_rabbitmq_integration.py -q --no-cov -o addopts=''
.venv/bin/python -m pytest backend/tests/infra/test_rabbitmq_bootstrap.py --cov=infra.rabbitmq.bootstrap --cov-branch --cov-fail-under=80 -o addopts='' -q
```

A integração cria um projeto Docker aleatório `coldsafe-b207-*`, dois volumes
novos, credenciais temporárias e porta AMQP aleatória somente em loopback.
Deriva os serviços do Compose real e constrói as imagens a partir de
`infra/rabbitmq` no próprio projeto. Configuração e bootstrap entram nas imagens,
sem montagem de arquivos do host durante a execução.
No `finally`, remove apenas esse projeto e esses volumes. Nunca monta volumes
pessoais, não inicia o restante da aplicação e não modifica `.env`.
Requer Docker e download/cache das duas imagens base fixadas. Sem a variável opt-in,
os testes reais ficam explicitamente skipped.

Fontes oficiais verificadas em 13/10/2026:
[import de definições](https://www.rabbitmq.com/docs/definitions),
[permissões](https://www.rabbitmq.com/docs/access-control),
[hash de senha](https://www.rabbitmq.com/docs/passwords),
[quorum, delayed retry e DLX](https://www.rabbitmq.com/docs/quorum-queues),
[Pika](https://github.com/pika/pika).
