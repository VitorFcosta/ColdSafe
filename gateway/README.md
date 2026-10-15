# Gateway MQTT ↔ AMQP — B2-11

Serviço Python opcional do perfil `aiot`. Transporta somente v3: telemetria e ACK
do Mosquitto para RabbitMQ; comandos da fila `coldsafe.gateway` para Mosquitto.
Não declara topologia nem conecta a API ao MQTT neste fluxo. A API v1/v2 conserva
seu transporte anterior. O [gravador B2-12](../writer/README.md) persiste telemetria
em fila própria; entrega Web v3 continua posterior.

## Preparar e iniciar

1. Prepare os segredos pelo [procedimento existente](../docs/configuration.md).
   `MQTT_GATEWAY_PASSWORD` e `RABBITMQ_GATEWAY_PASSWORD` são senhas distintas.
   Recrie o inicializador/broker MQTT se a conta ainda não foi provisionada,
   seguindo o [README do simulador](../simulator/README.md).
2. Cadastre `sim-lab-01` pela API existente, em ambiente privado. PostgreSQL deve
   estar inicializado pelas migrações atuais do backend. Configure
   `GATEWAY_OWNER_USER_ID` com o UUID real do proprietário esperado desta instância.
   Esse UUID não é senha nem sessão HTTP.
3. Preencha `SIMULATOR_CATALOG_DIR/catalog.json` conforme o cadastro. Gateway e
   simulador montam o mesmo arquivo em leitura. IDs fictícios do exemplo só
   funcionam no ensaio descartável, onde são cadastrados explicitamente.
4. Confira e inicie:

   ```sh
   docker compose --profile aiot --profile simulator config --quiet
   docker compose --profile aiot --profile simulator up -d --build gateway simulator
   docker compose logs --tail 30 gateway
   ```

Parar apenas o gateway: `docker compose stop gateway`. Preserve `gateway-state`:
contém eventos pendentes, identidades processadas e erros privados. A imagem cria
`/state` como `0700`, UID/GID `65532`; o processo usa umask `077`, filesystem em
leitura e volume próprio. Não publica portas nem entrega credenciais à API/simulador.

PostgreSQL é consultado com parâmetros vinculados, timeout e transações read-only:
dispositivo ativo → ambiente → proprietário esperado. Usa os parâmetros PostgreSQL
existentes do Compose; a tarefa não cria papel SQL. Read-only da conexão não
substitui permissões restritas de um papel PostgreSQL em produção.
Equipamento/sensores/atuadores são conferidos contra o catálogo privado; ainda não
há tabelas/API dessas entidades. A mensagem nunca cadastra nem redefine vínculos.
A ACL suporta somente `sim-lab-01`. Não iniciar réplicas com o mesmo client ID.

## Entrega e recuperação

- JSON UTF-8 estrito, limite de 8192 bytes antes de decodificar, schemas v3 com
  `FormatChecker`, tópico/key/cadastro, QoS 1 e `retain=false`. Rejeita labels,
  campos extras, identidade trocada e números inválidos.
- `ingress` guarda entrada canônica e evento aceito. Commit SQLite com
  `synchronous=FULL` precede ACK MQTT. `received_at` é preenchido uma vez;
  duplicata conserva o primeiro aceite após restart. Reusar ID com outro corpo
  ou entre comandos e entradas MQTT é erro permanente.
- Saída RabbitMQ persistente com `mandatory=True`, publisher confirm,
  `message_id=event_id` e correlação. Só então marca `sent=1`. Uma queda entre
  confirmação e marcação pode reenviar o mesmo evento; consumidores devem
  deduplicar por `(consumer, event_id)`.
- Comando exige metadados AMQP coerentes, escopo, atuador, origem, correlação e
  prazo de 30 s. `commands` registra o original antes de publicar. Só PUBACK MQTT
  positivo permite marcar enviado e dar ACK AMQP. Duplicata enviada não republica;
  duplicata tardia idêntica já enviada pode ser reconhecida sem atuação. Comando
  ainda não enviado e expirado é recusado. MQTT recebe também expiração.
- ACK exige comando previamente aceito e mesmo comando/atuador/escopo. ACK
  tardio/divergente é relato auditável; gateway não produz `confirmed`, status ou
  timeout de negócio. PUBACK nunca significa atuação.
- Comando inválido vai à DLQ sem requeue. Falha transitória usa
  `basic_reject(requeue=True)`, até três tentativas, com backoff quorum de 1 s/2 s.
  Última falha emite `RETRY_EXHAUSTED` e rejeição definitiva. Não republica comando
  em AMQP, não zera contador nem cria loop entre brokers.
- `errors` conserva transporte, rota e bytes originais no SQLite privado e emite
  `processing_error` sanitizado no bus. DLQ conserva originais AMQP/propriedades.
  Sem identidade validada, erro tem escopo/source nulos. Payload, rota privada,
  segredo e stack não entram no evento nem log.
- Reconexão AMQP drena o diário. PostgreSQL indisponível mantém MQTT sem ACK.
  Sessão MQTT dura 24 h; inscrição só em telemetria/ACK; ReceiveMaximum 16 e fila
  local limitada. Mensagem de conexão antiga não confirma MID de conexão nova.
  Fila excedida/diário cheio interrompem o processo sem confirmar dados não gravados.

## Testar sem tocar na pilha pessoal

Com Python e o lock dev do backend instalados, na raiz:

```sh
.venv/bin/python -m pytest backend/tests/infra/test_gateway.py backend/tests/infra/test_gateway_runtime.py --cov=gateway --cov-branch --cov-fail-under=80 -o addopts='' -q
COLDSAFE_GATEWAY_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_gateway_integration.py --no-cov -o addopts='' -q
```

A integração constrói os serviços do Compose em projeto Docker descartável
`coldsafe-b211-*`, PostgreSQL migrado/cadastro fictício, senhas temporárias,
portas aleatórias em loopback e volumes novos. Cleanup remove só esse projeto;
não lê `.env` pessoal. Sem opt-in, é explicitamente pulada. `-o addopts=''` evita
a cobertura padrão de `backend/app`, que não contém o gateway.

## Limites

Diário limitado a 16.384 páginas SQLite (aproximadamente 64 MiB para banco novo),
sem expurgo: conservar identidades evita reaceitar duplicatas como novas.
Mantém entrada e saída, portanto pode encher em poucas horas a 1 Hz; journal
transitório também ocupa disco. Antes de uso prolongado, implementar arquivamento
com política de retenção/deduplicação explícita. Para copiar/inspecionar, parar
gateway e usar backup SQLite; não apagar diário nem reutilizar volume de outro dono.

Não há transação distribuída entre SQLite, brokers e atuador. Queda após atuação
e antes do PUBACK permite reenviar o mesmo comando válido. O simulador usa estado
explícito e deduplica em memória; seu restart perde o cache. Não há garantia de
atuação exatamente uma vez entre falhas. Sessão MQTT vencida, volume perdido ou
queda antes do primeiro aceite podem perder dados da borda.
Autorização HTTP v3, status/timeout durável, regras e dashboard são posteriores.
Persistência InfluxDB está no [gravador B2-12](../writer/README.md).

APIs conferidas nas fontes primárias: [ACK manual/sessão Paho](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[confirms Pika](https://pika.readthedocs.io/en/stable/modules/adapters/blocking.html).
Topologia/retry: [infra RabbitMQ](../infra/rabbitmq/README.md).
