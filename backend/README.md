# Backend

A B2-13 acrescenta consumidor e entrega privada AIoT v3, habilitados explicitamente
por `compose.aiot.yaml`. Regras, comandos e auditoria são transacionais no PostgreSQL;
inbox deduplica eventos e outbox conserva saídas até confirmação AMQP. LED manual
e buzzer automático usam RabbitMQ → gateway; a API não publica MQTT no fluxo v3.
O fluxo legado MQTT v1/v2 continua separado.

Rotas e semântica estão em [contratos AIoT](../contracts/aiot.md#persistência-e-recuperação-http-v3--b2-13).
Operação no [guia de configuração](../docs/configuration.md#api-aiot-opcional-b2-13).
Com AIoT habilitado, readiness também exige as duas conexões AMQP. O histórico
HTTP v3 recupera eventos processados no PostgreSQL e informa `pending/persisted`;
WebSocket só entrega leituras com prova de gravação InfluxDB.

A B2-14 acrescenta contexto/limites ao resumo, períodos ou janela UTC no histórico,
consulta de alertas por intervalo e consulta privada de comando por UUID para o
dashboard. São extensões das rotas v3; nenhuma migração ou dependência nova.

A B2-15 acrescenta `GET /api/v3/messaging`, autorizado pelo papel admin atual
no PostgreSQL. Consulta a Management API por credencial exclusiva, limita os
campos às nove filas do produto e retorna contagens, consumidores e taxas com
`sampled_at`. Não lê mensagens. As métricas são agregadas da infraestrutura,
não filtradas por dispositivo/proprietário; viewer/operator recebem 403.
Falhas do broker retornam 503 sanitizado; sem credencial, a rota não é instalada.
Configuração e isolamento
estão em [Mensageria](../docs/configuration.md#mensageria-b2-15); sem dependência
ou migração nova.

A B2-16 acrescenta `GET /api/v3/messaging/messages`, também admin, mas com
resumos filtrados pelo dono atual do dispositivo/ambiente. O observador consome
somente cópias da fila `observability`; não retira originais da DLQ ou do writer.
Limita a memória a 100 eventos + 100 mensagens mortas, expõe conexão/atualidade
e metadados permitidos (IDs, tipo, horários, origem, motivo/erro), nunca corpos
brutos. Amostras desaparecem ao reiniciar; a DLQ é preservada.
Configuração e limites em [amostras privadas](../docs/configuration.md#amostras-privadas-b2-16).

A B2-17 acrescenta jobs privados com `POST /api/v3/jobs` (admin, `202`),
consulta por UUID e progresso HTTP/SSE autenticado. Job e outbox são atômicos;
AMQP confirma publicação e execução antes do ACK. Workers de geração e treino
compartilham um advisory lock PostgreSQL e retomam contadores duráveis.
Configuração em [jobs](../docs/configuration.md#jobs-assíncronos-b2-17),
contrato em [HTTP de jobs](../contracts/aiot.md#jobs-http-e-progresso-sse--b2-17).
Executores de geração massiva/ML ainda pertencem às próximas tarefas: ausência
de executor produz `failed`, nunca um resultado fictício.

Esta área contém a ingestão MQTT, a classificação das leituras, a persistência no
InfluxDB, a estrutura relacional PostgreSQL e a API FastAPI.

Na inicialização, `app/repositories/postgres.py` aplica em transação as migrações
versionadas em `migrations/`. O PostgreSQL guarda usuários,
sessões, ambientes, dispositivos, regras, alertas, comandos e auditoria;
leituras antigas continuam no InfluxDB. O readiness exige conexão com os dois
bancos e com o MQTT.

As versões 004–005 acrescentam papéis e metadados privados de jobs, datasets,
modelos e ativação por proprietário. A versão 006 acrescenta identificação de
sessões JWT, limites de login e tickets WebSocket. O [guia de migrações](migrations/README.md)
explica propriedade, backup e recuperação. A persistência prepara o AIoT;
workers de jobs estão na B2-17; cálculo e treino/inferência continuam posteriores. Autenticação e
permissões atuais estão no [guia de segurança](../docs/aiot/tasks/B2-06.md).

A primeira implementação do domínio está em `app/domain/telemetry.py`. Ela transforma
bytes MQTT não confiáveis em um `TelemetryPayload` estrito e imutável, rejeitando
campos ausentes ou extras, tipos incorretos, números não finitos e valores fora dos
limites técnicos. Mensagens maiores que 1 KiB são recusadas antes do parse para
limitar consumo de CPU e memória na fronteira MQTT.

O processo executável está em `app/main.py`. Ele valida as variáveis de ambiente,
inicia o assinante MQTT, fecha os recursos no desligamento e expõe:

- cadastro, login e logout em `/api/v1/auth/`;
- ambientes, dispositivos e regras em `/api/v1/`;
- `GET /api/v1/monitoring/summary`, `GET /api/v1/readings` e `GET /api/v1/alerts`;
- `POST /api/v1/devices/{id}/led/commands` e `GET /api/v1/commands/{id}`;
- `WS /api/v1/events?device_id=...`;
- `GET /health/live` e `GET /health/ready`.

O bloco 2 acrescenta `POST /api/v1/auth/register`, `/login` e `/logout`, com
JWT Bearer revogáveis de 24 horas; rotas REST para ambientes, dispositivos
e limites. `DELETE /api/v1/devices/{id}` desativa sem apagar o histórico. O
OpenAPI executável em `/openapi.json` lista os corpos e métodos completos.

Resumo e histórico aceitam `device_id` MQTT e exigem sessão do proprietário.
Sem `device_id`, o resumo seleciona `esp32-lab-01`, ainda sujeito à mesma
autorização; se não pertencer à conta, a resposta é `404`.
Dispositivos desativados mantêm consultas históricas, mas deixam de aceitar
telemetria. Os limites por ambiente são persistidos em `environment_rules` e
usados na classificação de novas leituras; as regras antigas por dispositivo
foram preservadas na migração. A interface de login e seleção de dispositivo
já usa essas rotas. `/auth/me` consulta o papel atual; administrador pode alterar
papéis em `PATCH /auth/users/{id}/role`, com auditoria, sem acessar dados alheios.
Visualizador lê seus dados; operador/administrador também escrevem nos próprios
ambientes. Cadastro público não escolhe papel. Novos hashes usam bcrypt; login
Argon2 antigo continua válido, sem truncar senhas longas. Limite de login:
10 tentativas por email e 50 por IP em 15 minutos, incluindo sucessos.

`POST /api/v1/auth/ws-ticket` recebe Bearer e `device_id`, devolvendo um ticket
de até 60 segundos. WebSocket envia somente `{ticket}` no primeiro frame;
URL contém apenas `device_id`. Eventos só são enviados após verificar sessão e
propriedade; a conexão é encerrada quando a sessão deixa de ser válida. Ao
reconectar, o cliente usa REST para recuperar o estado que pode ter perdido.

Os erros públicos usam envelopes estáveis e não expõem stack trace, token, payload
ou endereço interno.

Na telemetria v2, o assinante separa os dispositivos por tópico. O InfluxDB
mantém as leituras; PostgreSQL guarda o ciclo dos alertas, os comandos e a
auditoria. Buzzer automático respeita os limites do ambiente e a margem de
recuperação. Um comando LED publicado fica pendente até receber confirmação;
após 30 segundos sem ela, o estado é `unconfirmed`.
