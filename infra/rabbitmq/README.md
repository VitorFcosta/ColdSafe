# RabbitMQ — infraestrutura B2-07

O Compose prepara o broker interno `rabbitmq:5672`, vhost `coldsafe`, com
RabbitMQ `4.3.6-management-alpine`. Não publica AMQP nem management no host.
O backend v1/v2 continua no MQTT. O [gateway B2-11](../../gateway/README.md) já
consome comandos e produz telemetria/ACK/erros; demais serviços v3 são posteriores.
Estas filas prontas não provam os consumidores de negócio.

## Preparação e segredos

Preencha as dez variáveis `RABBITMQ_*_PASSWORD` de `.env.example` no `.env`
privado: senhas aleatórias distintas, com pelo menos 32 caracteres. O inicializador
offline recusa valores ausentes, curtos, repetidos ou `REPLACE_WITH_...`.
Nenhuma credencial pessoal é alterada pelos testes. O broker não recebe as senhas
em seu ambiente; recebe hashes SHA-256 com salt aleatório num volume privado.
As identidades não possuem tags administrativas; não existe `guest` no volume novo.

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
| writer | `coldsafe.writer` | telemetry | processing_error |
| inference | `coldsafe.inference` | telemetry, model_activation | prediction, model_status, processing_error |
| delivery | `coldsafe.delivery` | telemetry, ack, prediction, command_status, alert, freshness, job_progress, model_status, processing_error | processing_error |
| commands | `coldsafe.commands` | telemetry, ack, prediction, freshness | command, command_status, alert, freshness, processing_error |
| generation | `coldsafe.generation` | job_requested com header generation | job_progress, processing_error |
| training | `coldsafe.training` | job_requested com header training | job_progress, model_status, processing_error |
| observability | `coldsafe.observability` | `v3.#`, cópia própria | nenhum |
| api | nenhuma | nenhum | command, job_requested, model_activation, processing_error |
| audit | `coldsafe.dlq` | originais privados com falha | nenhum |

A observabilidade consome sua cópia; não tira mensagens das filas de negócio e
não acessa a DLQ. `audit` é uma identidade de transporte reservada à auditoria,
sem conceder acesso a usuários HTTP. A API futura precisa autorizar cada consulta
antes de revelar qualquer dado. O broker limita serviços/tipos, não propriedade
de usuário ou catálogo de dispositivos: essa validação continua no consumidor.

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
e idempotente. Integração com bancos, deduplicação e eventos sanitizados de erro
ainda pertencem aos serviços futuros; não confirmar uma leitura para WebSocket
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
