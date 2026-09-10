# Evidência de ensaio da demonstração completa

## Origem

Ensaio executado em 10/09/2026 para a tarefa CS-38 do Notion.

Critério de aceite: o roteiro completo funciona no computador da apresentação,
inclusive depois de reiniciar a composição, sem perder a telemetria persistida.

## Resultado

**PASS** — o fluxo ESP32/Wokwi → MQTT → FastAPI → InfluxDB → API → dashboard
funcionou no computador da apresentação. Os serviços reiniciaram com sucesso e
uma leitura registrada antes do reinício permaneceu disponível depois dele.

## Ambiente validado

- macOS 26.6.2;
- Docker 29.3.0;
- Docker Compose 5.1.0;
- Python 3.13.15;
- ESP32 com PlatformIO `espressif32@7.0.1`;
- imagens e dependências fixadas nos arquivos versionados do projeto.

O frontend da composição usa Node 24.20.0, conforme a versão fixada no projeto.
O Node disponível diretamente no terminal do host era 22.19.0; por isso, ele
não deve ser usado como referência para reproduzir o ambiente local. Esse desvio
não afeta o roteiro da apresentação, que executa o frontend pelo Docker.

## Roteiro executado

1. A configuração foi validada com `docker compose config --quiet`.
2. Os seis testes E2E do dashboard foram executados no Chromium.
3. O firmware foi compilado com:

   ```bash
   ~/.platformio/penv/bin/pio run --project-dir firmware
   ```

4. Uma leitura MQTT controlada de `7,38 °C` e `58,38%` foi publicada com QoS 1
   para `esp32-lab-01`.
5. A API confirmou a leitura como `normal`, com timestamp
   `2026-09-10T20:16:56.047109Z`.
6. A composição foi encerrada sem apagar volumes:

   ```bash
   docker compose down
   ```

7. A composição foi reconstruída e iniciada novamente:

   ```bash
   docker compose up -d --build --wait --wait-timeout 180
   ```

8. O histórico retornou a mesma leitura, com o mesmo timestamp, depois do
   reinício.
9. O Wokwi retomou as publicações e a API recebeu uma nova leitura de `6,9 °C`
   e `62,1%`.
10. A temperatura do DHT22 simulado foi alterada para `7,9 °C`.
11. A API classificou a nova leitura como `attention`, e o dashboard exibiu
    `Atenção`, `7,9 °C`, `62,1%` e o histórico atualizado.
12. O sensor foi restaurado para `6,9 °C`; a API voltou ao estado `normal`.

## Evidências observadas

| Verificação | Resultado |
| --- | --- |
| E2E do dashboard | 6 de 6 testes passaram |
| Compilação do firmware | PASS |
| MQTT QoS 1 até a API | PASS |
| Encerramento sem `--volumes` | PASS |
| Inicialização após o encerramento | PASS |
| Persistência da leitura após reinício | PASS |
| Mosquitto, InfluxDB, backend e frontend | `healthy` |
| `mosquitto-init` | `Exited (0)` |
| Liveness, readiness e frontend | HTTP 200 |
| Mudança do DHT22 refletida no dashboard | PASS |

## Cuidados para a apresentação

- Seguir o procedimento canônico em [`../runbook.md`](../runbook.md).
- Confirmar Docker iniciado, portas livres e Wokwi conectado antes de começar.
- Não usar `docker compose down --volumes`; isso apagaria os dados persistidos.
- Não expor `.env`, `firmware/include/secrets.h` ou credenciais durante a
  apresentação.
- Manter uma leitura recente visível antes de demonstrar a mudança do DHT22.

## Conclusão

O critério de aceite da CS-38 foi cumprido no computador da apresentação. O
roteiro completo foi exercitado com infraestrutura real, simulador ESP32,
mudança do sensor, atualização do dashboard, reinício dos containers e prova de
persistência.
