# Backend

Esta área contém a ingestão MQTT, a classificação das leituras, a persistência no
InfluxDB, a estrutura relacional PostgreSQL e a API FastAPI.

Na inicialização, `app/repositories/postgres.py` aplica em transação as migrações
versionadas em `migrations/`. O PostgreSQL guarda usuários,
sessões, ambientes, dispositivos, regras, alertas, comandos e auditoria;
leituras antigas continuam no InfluxDB. O readiness exige conexão com os dois
bancos e com o MQTT.

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
sessões Bearer revogáveis de 24 horas; rotas REST para ambientes, dispositivos
e limites. `DELETE /api/v1/devices/{id}` desativa sem apagar o histórico. O
OpenAPI executável em `/openapi.json` lista os corpos e métodos completos.

Resumo e histórico aceitam `device_id` MQTT e exigem sessão do proprietário.
Sem `device_id`, o resumo seleciona `esp32-lab-01`, ainda sujeito à mesma
autorização; se não pertencer à conta, a resposta é `404`.
Dispositivos desativados mantêm consultas históricas, mas deixam de aceitar
telemetria. Os limites por ambiente são persistidos em `environment_rules` e
usados na classificação de novas leituras; as regras antigas por dispositivo
foram preservadas na migração. A interface de login e seleção de dispositivo
já usa essas rotas. Eventos WebSocket só são enviados após verificar sessão e
propriedade; a conexão é encerrada quando a sessão deixa de ser válida. Ao
reconectar, o cliente usa REST para recuperar o estado que pode ter perdido.

Os erros públicos usam envelopes estáveis e não expõem stack trace, token, payload
ou endereço interno.

Na telemetria v2, o assinante separa os dispositivos por tópico. O InfluxDB
mantém as leituras; PostgreSQL guarda o ciclo dos alertas, os comandos e a
auditoria. Buzzer automático respeita os limites do ambiente e a margem de
recuperação. Um comando LED publicado fica pendente até receber confirmação;
após 30 segundos sem ela, o estado é `unconfirmed`.
