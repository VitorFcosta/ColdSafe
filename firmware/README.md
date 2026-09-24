# Firmware ColdSafe (ESP32 + Wokwi)

O mesmo código gera dois ESP32 independentes: `esp32-lab-01` (`esp32dev`, porta serial 4000) e `esp32-lab-02` (`esp32dev-02`, porta 4001).

## Configuração local

1. Instale PlatformIO IDE e Wokwi Simulator no VS Code. A simulação local do Wokwi exige uma licença ativa.
2. Configure `firmware/include/secrets.h` localmente. O arquivo é ignorado pelo Git. Use `secrets.example.h` como modelo, preservando as demais configurações que você já possui.
3. `MQTT_PASSWORD` corresponde ao usuário existente `coldsafe-device` do primeiro ESP32. Para o segundo, acrescente **ao seu secrets.h local** a macro `COLDSAFE_DEVICE_02_PASSWORD_CONFIGURED` e a constante `MQTT_DEVICE_02_PASSWORD` com o valor de `MQTT_DEVICE_02_PASSWORD` do `.env`. A senha do segundo usuário deve ser diferente da primeira. Sem essa configuração, o segundo binário compila com a senha antiga, mas não autentica no broker atualizado.
4. Inicie os serviços pelo Docker Compose antes de abrir as simulações.

Compile os dois firmwares:

```bash
~/.platformio/penv/bin/pio run --project-dir firmware -e esp32dev -e esp32dev-02
```

Abra `firmware/` e `firmware/device-02/` em janelas separadas do VS Code e execute **Wokwi: Start Simulator** em cada uma. Os dois usam o Wi-Fi `Wokwi-GUEST` e o broker `host.wokwi.internal`.

## Circuito

| Componente | Pino ESP32 | Função |
| --- | --- | --- |
| DHT22 SDA | GPIO 15 | Temperatura e umidade |
| Fotoresistor AO | GPIO 34 (ADC1) | Luminosidade relativa |
| LED com resistor de 220 Ω | GPIO 18 | Controle manual |
| Buzzer | GPIO 19 | Controle automático pelo backend |

DHT22 e fotoresistor usam 3V3 e GND. LED e buzzer têm retorno em GND. A luminosidade é uma porcentagem relativa calibrada pelos extremos ADC no firmware: 0 escuro, 100 claro. Para sensor físico, ajuste os dois extremos no código após medir o hardware.

## MQTT v2

Cada dispositivo publica a cada 5 segundos em `coldsafe/v2/devices/<device_id>/telemetry` com QoS 1. A leitura contém `schema_version: 2`, `device_id`, `temperature_c`, `humidity_percent` e `light_percent`. Uma leitura fora dos limites do contrato é descartada, sem republicar o valor antigo. O backend ainda pode ler o histórico v1; este firmware novo publica v2.

O ESP32 assina `coldsafe/v2/devices/<device_id>/commands` com QoS 1. Só aceita LED com origem `manual` e buzzer com origem `automatic`. Após aplicar o estado explícito, publica `coldsafe/v2/devices/<device_id>/acks` com QoS 1 e o mesmo `command_id`. Comando inválido com ID, atuador e destino reconhecíveis recebe `rejected`/`INVALID_COMMAND`. Repetição recente de `command_id` reenvia a confirmação sem reaplicar o atuador. O histórico de duplicatas guarda os últimos 8 comandos em RAM; um reinício limpa esse histórico. Ligar/desligar por estado explícito continua idempotente.

## Verificação manual

- Ajuste temperatura, umidade e luz em um Wokwi por vez. Confira as leituras no Serial Monitor e no histórico do respectivo dispositivo.
- Envie um comando válido de LED pela API e observe LED, log serial e confirmação. Repita o mesmo `command_id` por MQTT e confirme que o estado não é reaplicado.
- Provoque temperatura fora da faixa e retorno à faixa de recuperação. Confira que o backend envia os comandos automáticos e que o buzzer responde.
- Reinicie o Mosquitto; ambos os ESP32 devem reconectar e assinar novamente seus próprios tópicos.
- Com clientes MQTT autenticados como cada dispositivo, tente ler os comandos do outro e publicar no tópico dele. A ACL deve negar ambas as operações.
