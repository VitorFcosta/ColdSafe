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

- `GET /api/v1/monitoring/summary`;
- `GET /api/v1/readings`;
- `GET /health/live`;
- `GET /health/ready`.

O bloco 2 acrescenta `POST /api/v1/auth/register`, `/login` e `/logout`, com
sessões Bearer revogáveis de 24 horas; rotas REST para ambientes, dispositivos
e limites. `DELETE /api/v1/devices/{id}` desativa sem apagar o histórico. O
OpenAPI executável em `/openapi.json` lista os corpos e métodos completos.

Resumo e histórico aceitam `device_id` MQTT e exigem sessão do proprietário
quando o dispositivo está cadastrado. A consulta antiga sem `device_id` segue
disponível para `esp32-lab-01` apenas enquanto ele não tiver proprietário.
Dispositivos desativados mantêm consultas históricas, mas deixam de aceitar
telemetria. Os limites por ambiente são persistidos em `environment_rules` e
usados na classificação de novas leituras; as regras antigas por dispositivo
foram preservadas na migração. A interface de login e seleção de dispositivo
pertence a uma etapa posterior do roadmap.

Os erros públicos usam envelopes estáveis e não expõem stack trace, token, payload
ou endereço interno.
