# Apresentação de setembro — histórico

Para novembro, usar o [roteiro AIoT](../aiot/presentation.md).

**28/09/2026 · 1 apresentador · máximo de 5 minutos · sem slides.** Roteiro de 4min40, com 20 segundos de margem. Apresentar a aplicação funcionando.

Voltar para <mention-page url="https://app.notion.com/p/3ced67001da980518b3ee591cb27882c">ColdSafe</mention-page>. Referência técnica: [📘 Documentação do projeto](../README.md).

# 1. Antes de começar

Deixar a conta proprietária autenticada, os dois Wokwi conectados e as janelas posicionadas. Executar a demonstração em apenas um dispositivo; o outro permanece disponível para mostrar a separação dos ambientes.

**Ainda precisa de ensaio real:** clique no dashboard → LED → confirmação, e temperatura → regra → buzzer → recuperação. Comandos MQTT diretos e testes com API simulada não substituem esse percurso. A criação deste roteiro não conclui o ensaio.

# 2. Roteiro cronometrado

| Tempo | Ação na tela | Fala sugerida |
| --- | --- | --- |
| 0:00–0:20 | Abrir diretamente o dashboard com uma leitura recente. | O ColdSafe monitora ambientes refrigerados. Evoluímos o monitoramento inicial com gerenciamento de dispositivos, novos sensores, comunicação em tempo real e atuação manual e automática. |
| 0:20–0:45 | Abrir Ambientes e dispositivos. Mostrar os dois ESP32 e os limites. Salvar uma pequena alteração no nome de um ambiente de demonstração. | Cada ambiente possui dispositivos e limites configuráveis. Os cadastros e as regras ficam no PostgreSQL. |
| 0:45–1:25 | Mostrar Wokwi e dashboard lado a lado. Alterar umidade no DHT22 e luminosidade no fotoresistor; esperar os indicadores. | Usamos dois sensores: o DHT22 mede temperatura e umidade; o fotoresistor mede luminosidade. O ESP32 envia leituras por MQTT ao Mosquitto. O backend processa os dados e a interface atualiza sem recarregar. |
| 1:25–2:10 | Aumentar temperatura acima do limite; mostrar crítico, alerta e buzzer no Wokwi. Voltar à faixa de recuperação. | O backend compara a temperatura com os limites cadastrados. Fora da faixa, envia um comando automático para o buzzer. Na faixa de recuperação, o alarme é encerrado. |
| 2:10–2:45 | Expandir LED e buzzer. Clicar Ligar LED, mostrar LED aceso e confirmação; depois desligar. | Agora o caminho é Web → backend → MQTT → ESP32. O estado só é confirmado depois da resposta do dispositivo. |
| 2:45–3:15 | Mostrar gráfico, trocar período e abrir a tabela. Localizar a temperatura alterada. | As leituras ficam no InfluxDB e são consultadas por período. O gráfico usa Chart.js para mostrar a evolução da temperatura. |
| 3:15–4:30 | Percorrer as evidências técnicas preparadas na seção seguinte. | Estas são as evidências dos serviços e da comunicação que acabamos de utilizar. |
| 4:30–4:40 | Voltar ao dashboard em estado normal. | Demonstramos dois sensores, buzzer automático, LED manual, histórico e comunicação nos dois sentidos, com os serviços integrados pelo Docker Compose. |
| 4:40–5:00 | Margem para latência e troca de janela. | Não iniciar uma funcionalidade extra. |

# 3. Evidências técnicas em 75 segundos

Deixar os painéis e consultas prontos. Executar as consultas durante o ensaio e atualizá-las depois das ações da demonstração; mostrar valores correspondentes ao mesmo dispositivo, sem senhas ou tokens.

| Duração | Evidência | O que deve aparecer |
| --- | --- | --- |
| 10 s | Docker + Compose | Saúde dos cinco serviços: frontend, backend, Mosquitto, PostgreSQL e InfluxDB. O mosquitto-init é uma tarefa que termina com código 0. |
| 15 s | MQTT / Mosquitto | Mensagens reais de telemetry, commands e acks do ESP32 usado. A confirmação deve corresponder ao comando. |
| 20 s | FastAPI / REST / WebSocket | Documentação da API; resposta REST autenticada e mensagens recebidas na conexão WebSocket durante a alteração de sensor ou comando. |
| 20 s | PostgreSQL e InfluxDB | Registro do ambiente alterado no PostgreSQL e leitura recente em environment_reading no InfluxDB; comparar dispositivo, horário e valor com o histórico. |
| 10 s | Stack e GitHub | Dependências Vue 3, TypeScript, Vite e Chart.js; repositório com a versão utilizada na apresentação. |

**Atenção ao acesso aos bancos:** o Compose atual mantém PostgreSQL e InfluxDB na rede interna. Preparar consultas pelos recursos existentes dos containers; não presumir uma interface de banco aberta em [localhost](http://localhost).
**WebSocket:** mostrar mensagens recebidas; a primeira mensagem de autenticação contém a sessão e não deve ser projetada.
# 4. Checklist de preparação

- [ ] Login feito na conta que realmente possui os dispositivos.
- [ ] Dois Wokwi iniciados, conectados e enviando leituras recentes.
- [ ] Dashboard no dispositivo escolhido e controles de atuadores expandidos.
- [ ] Limites conferidos na gestão.
- [ ] Se a regra for 2–8 °C com margem de 0,5 °C, ensaiar 5 °C → 10 °C → 5 °C.
- [ ] Umidade e luz com mudanças visíveis já ensaiadas; luminosidade é percentual relativo, não lux.
- [ ] LED liga/desliga pelo dashboard e recebe confirmação.
- [ ] Buzzer liga por temperatura fora da faixa e desliga na recuperação.
- [ ] Histórico contém leituras recentes e o período correto está selecionado.
- [ ] Evidências de MQTT, REST/WebSocket e bancos prontas, sem credenciais na projeção.
- [ ] Serviços saudáveis e versão final correspondente no GitHub.
- [ ] Ensaio completo cronometrado abaixo de 5 minutos.
O firmware publica a cada **5 segundos**. Não narrar uma mudança como concluída antes de ela aparecer. O estado “Aguardando confirmação” pode ser breve; o importante é mostrar atuação e confirmação, sem provocar falha artificial para prolongá-lo.
# 5. Cobertura dos 10 critérios

| Critério do enunciado — 1 ponto cada | Onde demonstrar |
| --- | --- |
| Evolução e qualidade da aplicação | Abertura, gestão de ambientes/dispositivos e operação atual. |
| Pelo menos 2 sensores | DHT22 e fotoresistor variando no Wokwi e na Web. |
| Pelo menos 2 atuadores | LED e buzzer atuando na simulação. |
| Atuador automático | Temperatura fora da faixa acionando buzzer. |
| Atuador pela aplicação Web | Botão do LED, atuação e confirmação. |
| MQTT + Mosquitto bidirecional | Telemetria em um sentido; comando e ACK no retorno. |
| PostgreSQL e InfluxDB | Consulta de cadastro e de leitura, com correspondência à interface. |
| WebSocket, dashboard, gráficos e histórico | Atualização sem recarga, mensagens WebSocket e histórico com gráfico. |
| Docker + Compose | Cinco serviços saudáveis executando a integração. |
| Apresentação e funcionamento completo | Percurso real dentro do tempo, com explicação clara. |

O código conter uma tecnologia não garante o ponto: a avaliação considera seu funcionamento durante a apresentação.
# 6. Perguntas que o apresentador deve saber responder

Por que dois bancos?
PostgreSQL organiza entidades e relações, como conta, ambiente, dispositivo e regras. InfluxDB guarda as medições ao longo do tempo. O backend integra as duas responsabilidades.

Qual a diferença entre REST, WebSocket e MQTT?
REST atende consultas, cadastros e pedidos de comando. WebSocket entrega eventos à interface; ela também recupera o estado via REST. MQTT transporta telemetria, comandos e confirmações entre backend e ESP32, por meio do Mosquitto.

Por que a confirmação do comando importa?
A publicação no broker não prova que o ESP32 atuou. O ACK correlacionado comprova a aplicação do estado. Sem confirmação válida em 30 segundos, o comando fica sem confirmação.

Por que o buzzer pode continuar ligado abaixo de 8 °C?
Com máximo 8 °C e margem 0,5 °C, é preciso chegar à faixa interna, até 7,5 °C, para recuperar. Isso evita oscilações rápidas do alarme perto do limite.

O sistema refrigera o ambiente ou possui inteligência artificial?
Não. É um protótipo de monitoramento com uma regra explícita de temperatura, buzzer automático e LED manual. Não há controle de compressor ou inteligência artificial.

# 7. Contingência e limites

- Se um valor não mudar, conferir o dispositivo selecionado e aguardar a próxima publicação.
- Se o comando falhar, mostrar honestamente o estado sem confirmação e identificar o trecho interrompido. Não trocar por um comando direto alegando que foi acionado pela Web.
- Deixar reinícios, queda do broker e testes de isolamento para o ensaio completo ou perguntas; não acrescentá-los ao roteiro principal de 5 minutos.
- O vídeo da landing usa respostas simuladas. Pode explicar a interface, mas não prova o funcionamento integrado exigido.
- Uma pessoa conduz a demonstração; o enunciado continua exigindo que todos os integrantes conheçam a arquitetura e possam responder perguntas.
# 8. Registro do ensaio

Preencher após executar; manter os itens pendentes até observar o resultado.
- **Data e computador:** a preencher.
- **Apresentador:** a preencher.
- **Duração total:** a preencher.
- **LED pela Web e ACK:** a verificar.
- **Buzzer automático e recuperação:** a verificar.
- **Sensores, histórico, bancos e comunicação:** a verificar.
- **Falhas observadas e correções necessárias:** a registrar.
Atualizar a tarefa existente [CS-63](tasks/CS-63.md) com a evidência. Este roteiro deriva do enunciado fornecido pelo grupo e da inspeção do projeto em 27/09/2026.
