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
persistência. Esta evidência é do **primeiro bimestre** e não valida as novas
funções com duas contas e dois dispositivos.

## Roteiro do segundo bimestre — bloco 5

Esta seção é o roteiro para ensaiar a versão atual no computador da
apresentação. A evidência antiga acima não substitui a execução destes passos.
Use contas e dispositivos já cadastrados; não apague nem transfira dados
persistidos só para preparar o ensaio.

1. Confira `docker compose config --quiet` e
   `docker compose up -d --build --wait --wait-timeout 180`. Verifique os cinco
   serviços persistentes como `healthy` e `mosquitto-init` com saída `0`.
2. Compile os dois alvos com
   `~/.platformio/penv/bin/pio run --project-dir firmware -e esp32dev -e esp32dev-02`.
   Abra os dois projetos Wokwi descritos em [`firmware/README.md`](../../firmware/README.md).
3. Entre na conta proprietária e selecione, em sequência, os ambientes dos
   dispositivos `esp32-lab-01` e `esp32-lab-02`. Confirme temperatura, umidade
   e luminosidade independentes, sem recarregar a página. Use uma segunda conta
   para verificar a negação de acesso no passo 6; não transfira dispositivos
   persistidos para preparar o ensaio.
4. Mude a luz e a temperatura em apenas um simulador. Confirme atualização por
   WebSocket e histórico apenas do dispositivo escolhido. Provoque temperatura
   fora dos limites e recuperação; observe abertura/encerramento do alerta e
   buzzer ligar/desligar sem comandos repetidos a cada leitura.
5. Solicite LED pela interface. Observe `pending` antes do ACK e `confirmed`
   somente após a atuação no ESP32. Confira que um comando sem confirmação
   termina `unconfirmed`, nunca como sucesso presumido.
6. Faça tentativa direta de resumo, histórico, alertas, comandos e WebSocket
   dos dois dispositivos com a sessão da conta alheia. O acesso deve ser
   negado sem revelar dados dos dispositivos.
7. Filtre alertas por dispositivo/período e compare o período com o anterior de
   igual duração. Confira a seleção correta após alternar ambientes.
8. Pare e retome o Mosquitto. A falha deve ficar visível, os dois ESP32 devem
   reconectar e novas leituras devem voltar. Interrompa a conexão WebSocket no
   navegador e confira reconexão com restauração do estado por REST.
9. Anote um cadastro e uma leitura, execute `docker compose down` **sem
   `--volumes`**, suba novamente e confirme o mesmo cadastro no PostgreSQL e a
   mesma leitura no InfluxDB.
10. Refaça uma verificação curta das duas contas, LED, buzzer e histórico.
    Cada integrante deve conseguir explicar o papel de ESP32, MQTT, FastAPI,
    PostgreSQL, InfluxDB, REST, WebSocket e Vue sem slides.

Registre data, computador, integrantes, resultados e falhas observadas antes
de marcar a tarefa 24 como concluída. O teste automatizado de integração pode
comprovar backend e bancos, mas não substitui os dois Wokwi nem a explicação
dos integrantes.

### Verificações executadas em 26/09/2026

| Verificação | Resultado |
| --- | --- |
| Suíte Python sem credenciais de integração | 255 passaram, 9 ignorados; cobertura 82,72% |
| Suíte Python com bancos e broker reais, bucket de teste temporário | 263 passaram, 1 ignorado por exigir `API_TEST_URL` de uma pilha de ensaio legada; cobertura 92,59% |
| Teste integrado específico do bloco 5 | Passou com PostgreSQL e InfluxDB reais: duas contas e dispositivos com IDs únicos, isolamento REST/WebSocket, leitura, histórico, alerta, buzzer, LED pendente e comando sem confirmação |
| Quedas controladas | Readiness `503` com MQTT ou bancos parados; voltou a `200` após reinício |
| Persistência | Contagens PostgreSQL e timestamps das leituras dos dispositivos 01/02 permaneceram iguais após reinício dos serviços |
| Broker | Usuários MQTT 01/02 receberam `Not authorized` ao publicar no tópico alheio |
| Frontend | 57 testes, build e 19 testes Playwright passaram; cobertura 87,33% de instruções, 81,19% de ramos, 88,78% de funções e 91,81% de linhas |
| Firmware | `esp32dev` e `esp32dev-02` compilaram |
| Wokwi com dois ESP32 | Ambos iniciaram em janelas separadas, conectaram ao MQTT e publicaram com QoS 1 nos tópicos próprios; o InfluxDB registrou leituras de `esp32-lab-01` às 18:02:52 UTC e de `esp32-lab-02` às 18:02:54 UTC |
| Segunda conta contra dispositivos existentes | Conta temporária com senha gerada tentou resumo, histórico, alertas, detalhe e comando LED para os dois ESP32; as dez requisições retornaram `404`. A conta temporária foi removida sem mudar o proprietário dos dispositivos |
| Auditoria de dependências | `npm audit` e `pip-audit` no lock de desenvolvimento: nenhuma vulnerabilidade conhecida |

O teste integrado usa a entrada de telemetria do runtime com IDs únicos e
clientes reais dos bancos; o transporte MQTT e a ACL foram verificados à parte.
Os IDs `esp32-lab-01` e `esp32-lab-02` já pertenciam a contas persistidas e não
foram reassociados. As contas temporárias foram removidas. Dez IDs de teste
gerados em execuções anteriores no bucket principal foram identificados e suas
leituras removidas por ID exato; nenhuma leitura anterior foi alterada. A
suíte final usou um bucket temporário, removido ao terminar. Para repetir o
teste integrado, use infraestrutura de teste descartável e defina
`POSTGRES_TEST_PASSWORD`, `INFLUXDB_TEST_TOKEN` e um
`INFLUXDB_TEST_BUCKET` exclusivo para testes,
com `POSTGRES_TEST_HOST/PORT/DB/USER` e `INFLUXDB_TEST_URL/ORG` se os
valores diferirem do Compose de integração. Os demais testes podem ser
executados sem essas variáveis; nesse caso, o teste integrado é ignorado.
O teste legado `test_runtime_pipeline_integration.py` espera uma API com
`esp32-lab-01` sem proprietário e por isso não foi executado sobre os dados
persistidos atuais. O fluxo autenticado foi coberto pelo teste integrado deste
bloco; o transporte MQTT real foi verificado separadamente.

**Ainda pendente:** comprovar visualmente a atuação de LED/buzzer e a reconexão
de ambos os Wokwi após uma queda, percorrer os dez passos
com o grupo e registrar quem explicou cada parte. O Node do host era `22.19.0`;
as verificações locais passaram, mas a referência fixada para a aplicação é
`24.20.0` no Docker. O PlatformIO foi usado em ambiente temporário fora do
repositório. A publicação no GitHub depende de push posterior, fora deste bloco
de execução local.
