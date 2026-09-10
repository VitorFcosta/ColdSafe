# Infraestrutura local

O Docker Compose executa Mosquitto, InfluxDB, backend FastAPI e frontend Vue. O
serviço efêmero `mosquitto-init` prepara as credenciais do broker antes do
Mosquitto iniciar.

O procedimento canônico para preparar outro computador, criar o token restrito
do InfluxDB, subir os serviços, validar o sistema e diagnosticar falhas está em
[`../docs/runbook.md`](../docs/runbook.md).

## Preparar variáveis locais

Na raiz do projeto:

```bash
cp .env.example .env
```

Preencha os campos vazios com valores exclusivos para desenvolvimento. Use a
mesma senha escolhida para `MQTT_DEVICE_PASSWORD` ao configurar o firmware. O
backend deve receber um `INFLUXDB_TOKEN` exclusivo, com leitura e escrita
somente no bucket de telemetria; nunca reutilize o token administrativo.

## Credenciais MQTT

O `mosquitto-init` gera automaticamente o arquivo de senhas no volume nomeado
`mosquitto-auth`, usando `MQTT_BACKEND_PASSWORD` e `MQTT_DEVICE_PASSWORD` do
`.env`. Não crie um arquivo `passwords` manualmente.

## Subir e verificar

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

O Mosquitto fica disponível apenas em `127.0.0.1:1883`. No Wokwi, o endereço
equivalente é `host.wokwi.internal`. O InfluxDB não publica a porta `8086` no
host; o backend o acessa pela rede interna em `http://influxdb:8086`. A API e o
frontend ficam disponíveis somente no host em `127.0.0.1:8000` e
`127.0.0.1:5173`, respectivamente.

O Mosquitto participa de duas redes: a interna, para conversar com o backend, e
a rede de borda, necessária para publicar a porta no host. O InfluxDB
participa somente da rede interna. Consulte o runbook para os healthchecks e os
testes HTTP esperados.

## Parar sem apagar o histórico

```bash
docker compose down
```

Não use `docker compose down --volumes` no fluxo normal: essa opção apaga os
volumes nomeados e, com eles, o histórico do InfluxDB. As credenciais de
inicialização do InfluxDB só são aplicadas quando o volume está vazio.
