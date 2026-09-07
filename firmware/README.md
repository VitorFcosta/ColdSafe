# Firmware

Projeto PlatformIO do ESP32 com DHT22 para simulação no Wokwi.

## Pré-requisitos

- VS Code com as extensões PlatformIO IDE e Wokwi Simulator.
- Uma licença ativa do Wokwi para executar a simulação no VS Code
  (gratuita para projetos open source; comercial exige licença paga).

## Executar a simulação

1. Abra a raiz do projeto `ColdSafe` no VS Code.
2. No terminal da raiz, gere o firmware:

```bash
~/.platformio/penv/bin/pio run --project-dir firmware
```

3. Pressione `F1` e execute **Wokwi: Select Config File**.
4. Selecione `firmware/wokwi.toml`.
5. Execute **Wokwi: Start Simulator**.
6. No Serial Monitor, confirme leituras como:

```text
temperature_c=5.4 humidity_percent=62.1
```

Clique no DHT22 durante a simulação e altere temperatura ou umidade. A leitura
seguinte deve refletir o novo valor.

## Circuito

- DHT22 `VCC` → ESP32 `3V3`.
- DHT22 `GND` → ESP32 `GND`.
- DHT22 `SDA` → ESP32 `GPIO 15`.

Esta primeira fatia apenas lê o sensor localmente. Wi-Fi, MQTT e o gateway
privado serão adicionados nas próximas tarefas do backlog.
