# Backend

Esta área contém a ingestão MQTT, a classificação das leituras, a persistência no
InfluxDB e a API FastAPI.

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

Os erros públicos usam envelopes estáveis e não expõem stack trace, token, payload
ou endereço interno.
