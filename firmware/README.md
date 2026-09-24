# Firmware

Projeto PlatformIO do ESP32 com DHT22 para simulação no Wokwi.

## Pré-requisitos

- VS Code com as extensões PlatformIO IDE e Wokwi Simulator.
- Uma licença ativa do Wokwi para executar a simulação no VS Code
  (gratuita para projetos open source; comercial exige licença paga).
- Mosquitto local iniciado pelo Docker Compose.
- `firmware/include/secrets.h` preenchido com a mesma senha do usuário
  `coldsafe-device` configurado no broker.

## Executar as duas simulações

1. Abra a raiz do projeto `ColdSafe` no VS Code.
2. No terminal da raiz, gere os dois firmwares a partir do mesmo código:

```bash
~/.platformio/penv/bin/pio run --project-dir firmware -e esp32dev -e esp32dev-02
```

3. Abra `firmware/` e `firmware/device-02/` em duas janelas do VS Code.
4. Em cada janela, execute **Wokwi: Start Simulator**. Cada pasta tem seu
   próprio `wokwi.toml` e `diagram.json`.
5. Nos dois Serial Monitors, confirme a conexão MQTT, as leituras e publicações como:

```text
ColdSafe: MQTT conectado ao Mosquitto local
temperature_c=5.4 humidity_percent=62.1
ColdSafe: telemetria publicada em coldsafe/v1/telemetry com QoS 1
```

A primeira compilação usa o ID MQTT `esp32-lab-01` e a segunda,
`esp32-lab-02`. As portas seriais são 4000 e 4001, respectivamente. Mantenha
as duas janelas abertas e verifique que ambas continuam publicando. O usuário
MQTT e a senha são compartilhados nesta etapa; o broker diferencia as sessões
pelo ID do cliente. Cada mensagem inclui seu `device_id` para que o backend
armazene as leituras separadamente.

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
`firmware/include/secrets.h`, que é ignorado pelo Git. O `DEVICE_ID` nesse
arquivo serve como valor de reserva para compilações próprias sem a definição
`COLDSAFE_DEVICE_ID`; os dois ambientes acima definem seus IDs em
`platformio.ini`.
