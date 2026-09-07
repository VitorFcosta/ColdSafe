# Firmware

Projeto PlatformIO do ESP32 com DHT22 para simulação no Wokwi.

## Pré-requisitos

- VS Code com as extensões PlatformIO IDE e Wokwi Simulator.
- Uma licença ativa do Wokwi para executar a simulação no VS Code
  (gratuita para projetos open source; comercial exige licença paga).
- Mosquitto local iniciado pelo Docker Compose.
- `firmware/include/secrets.h` preenchido com a mesma senha do usuário
  `coldsafe-device` configurado no broker.

## Executar a simulação

1. Abra a raiz do projeto `ColdSafe` no VS Code.
2. No terminal da raiz, gere o firmware:

```bash
~/.platformio/penv/bin/pio run --project-dir firmware
```

3. Pressione `F1` e execute **Wokwi: Select Config File**.
4. Selecione `firmware/wokwi.toml`.
5. Execute **Wokwi: Start Simulator**.
6. No Serial Monitor, confirme a conexão MQTT, as leituras e publicações como:

```text
ColdSafe: MQTT conectado ao Mosquitto local
temperature_c=5.4 humidity_percent=62.1
ColdSafe: telemetria publicada em coldsafe/v1/telemetry com QoS 1
```

Clique no DHT22 durante a simulação e altere temperatura ou umidade. A leitura
seguinte deve refletir o novo valor. O firmware lê o sensor a cada 2 segundos e
publica o último valor válido a cada 5 segundos.

Para testar a reconexão, reinicie somente o serviço `mosquitto`. O firmware deve
tentar uma nova conexão em intervalos de 5 segundos e retomar as publicações sem
reiniciar o ESP32.

## Circuito

- DHT22 `VCC` → ESP32 `3V3`.
- DHT22 `GND` → ESP32 `GND`.
- DHT22 `SDA` → ESP32 `GPIO 15`.

O firmware conecta ao `Wokwi-GUEST`, acessa o Mosquitto local por
`host.wokwi.internal`, autentica como `coldsafe-device` e publica em
`coldsafe/v1/telemetry` com QoS 1. Credenciais reais permanecem somente em
`firmware/include/secrets.h`, que é ignorado pelo Git.
