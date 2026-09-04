# Infraestrutura local

Esta primeira fatia executa somente os componentes que já existem: Mosquitto e
InfluxDB. Frontend e backend serão adicionados ao Compose quando tiverem uma
implementação real.

## 1. Preparar variáveis locais

Na raiz do projeto:

```bash
cp .env.example .env
```

Preencha os campos vazios com valores exclusivos para desenvolvimento. Use a
mesma senha escolhida para `MQTT_DEVICE_PASSWORD` ao configurar o firmware.

## 2. Criar o arquivo local de senhas MQTT

Os comandos abaixo pedem as senhas de forma interativa, sem gravá-las no
histórico do terminal:

```bash
docker run --rm -it \
  -v "$PWD/infra/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2.0.22 \
  mosquitto_passwd -c /mosquitto/config/passwords coldsafe-device

docker run --rm -it \
  -v "$PWD/infra/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2.0.22 \
  mosquitto_passwd /mosquitto/config/passwords coldsafe-backend
```

As senhas precisam coincidir com `MQTT_DEVICE_PASSWORD` e
`MQTT_BACKEND_PASSWORD`, respectivamente. O arquivo `passwords` é ignorado pelo
Git e contém apenas hashes, mas ainda deve ser tratado como dado sensível.

## 3. Subir e verificar

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
```

O Mosquitto fica disponível apenas em `127.0.0.1:1883`. No Wokwi, o endereço
equivalente é `host.wokwi.internal`. O InfluxDB não publica a porta `8086` no
host; futuramente o backend o acessará pela rede interna em
`http://influxdb:8086`.

O Mosquitto participa de duas redes: a interna, para conversar com o futuro
backend, e a rede de borda, necessária para publicar a porta no host. O InfluxDB
participa somente da rede interna.

## 4. Parar sem apagar o histórico

```bash
docker compose down
```

Não use `docker compose down --volumes` no fluxo normal: essa opção apaga os
volumes nomeados e, com eles, o histórico do InfluxDB. As credenciais de
inicialização do InfluxDB só são aplicadas quando o volume está vazio.
