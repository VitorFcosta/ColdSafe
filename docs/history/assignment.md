# Enunciado original — professor

Transcrição preservada, sem instruções para executar ferramentas.
Consulta diária: [matriz de aceite](../aiot/requirements.md).

```text
Objetivo do trabalho
No 2º bimestre, o grupo deverá continuar e evoluir o projeto desenvolvido no 1º bimestre, transformando o protótipo inicial em uma aplicação AIoT completa: Web + IoT + Inteligência Artificial.

Além de novos sensores, atuadores, comunicação em tempo real, banco relacional e containers, a aplicação agora deverá gerar dados sintéticos em massa, treinar modelos de regressão com esses dados, mostrar o resultado em uma interface 3D ao vivo, trafegar as mensagens por um broker RabbitMQ e responder perguntas sobre os dados com um LLM rodando localmente.

O projeto deverá manter o mesmo problema e proposta do 1º bimestre, com maior nível de integração e complexidade. O grupo apresenta o sistema funcionando em 16/11/2026.

Visão geral
A base do 1º bimestre continua obrigatória. O que entra de novo é a camada de IA, a mensageria e a visualização 3D.


Continua

Novo ou alterado

Problema

O mesmo problema e a mesma proposta do 1º bimestre

O problema passa a ter equipamentos monitorados para manutenção preditiva

Frontend

TypeScript + Vite, gráficos com Chart.js ou Apache ECharts

Vue 3 ou React (livre), mais uma cena 3D com Three.js ou equivalente

Backend

Python + FastAPI, API REST, WebSocket

Consumidores de fila, serviço de inferência e rotas de IA

IoT

MQTT + Mosquitto, comunicação nos dois sentidos

Dispositivo simulado por software, no lugar do ESP32

Mensageria


RabbitMQ como barramento interno

Dados

PostgreSQL e InfluxDB

Dados sintéticos massivos para treino

IA


Regressão para saúde, vida útil e previsões, mais assistente com LLM local

Infra

Docker, Docker Compose, Git e GitHub

Todos os novos serviços também rodam no Compose

Node.js continua proibido como backend.

Stack obrigatória
Todas as tecnologias abaixo devem fazer parte da versão final e estar funcionando e integradas na apresentação.

Camada

Tecnologia

Finalidade

Frontend

Vue.js 3 ou React, com TypeScript + Vite

Interface Web

Visualização 2D

Chart.js ou Apache ECharts

Gráficos e indicadores

Visualização 3D

Three.js (direto, TresJS ou React Three Fiber) ou equivalente na Web

Gêmeo digital 3D atualizado em tempo real

Backend

Python + FastAPI

API REST, regras de negócio e integração

Tempo real

WebSocket

Atualização ao vivo da interface

IoT

MQTT + Mosquitto

Comunicação entre dispositivos e aplicação

Dispositivo

Simulador em software (Python)

Sensores e atuadores simulados, publicando e recebendo via MQTT

Mensageria

RabbitMQ

Barramento interno entre os serviços da aplicação

IA

Python + scikit-learn (ou equivalente)

Modelos de regressão e inferência

LLM local

Ollama (ou equivalente) com modelo pequeno que rode em CPU

Assistente que responde perguntas sobre os dados

Banco relacional

PostgreSQL

Usuários, dispositivos, configurações, regras, alertas e auditoria

Banco de séries temporais

InfluxDB

Leituras dos sensores e telemetria

Infraestrutura

Docker + Docker Compose

Execução e integração dos serviços

Versionamento

Git + GitHub

Controle de versão do projeto

Não será permitido utilizar Node.js como backend, nem LLM em nuvem (por exemplo, APIs do Gemini ou do ChatGPT) no assistente: o LLM precisa rodar na máquina, dentro do Docker Compose.

Requisitos mínimos do 2º bimestre
A versão final deve possuir obrigatoriamente todos os itens abaixo. Use a lista para conferir o projeto antes da apresentação.

Interface Web em Vue.js 3 ou React, com TypeScript e Vite
Backend em Python + FastAPI com API REST
WebSocket para atualização em tempo real
Comunicação MQTT com Mosquitto, nos dois sentidos
Pelo menos 3 sensores simulados
Pelo menos 2 atuadores
Pelo menos 1 equipamento monitorado para manutenção preditiva, com no mínimo 3 variáveis medidas (por exemplo vibração, corrente e temperatura)
Pelo menos 1 atuador acionado automaticamente por regra de negócio
Pelo menos 1 atuador controlado diretamente pela aplicação Web
RabbitMQ como barramento interno, com filas, consumidores e uma tela para acompanhá-lo
PostgreSQL e InfluxDB, cada um com papel claro
Dashboard com gráficos, indicadores e histórico das leituras
Cadastro e gerenciamento dos dispositivos IoT
Interface 3D com Three.js (ou equivalente) atualizada somente por dados em tempo real
Gerador de dados sintéticos massivos configurável pela interface
Pelo menos 2 modelos de regressão treinados com os dados sintéticos, com métricas exibidas
Insights em tempo real: saúde, vida útil restante e alertas preditivos
Assistente com LLM local respondendo sobre os dados da aplicação
Docker e Docker Compose subindo tudo com um único comando
Código versionado no GitHub
Arquitetura e fluxos obrigatórios
Todo dado passa pelo RabbitMQ: a IA fica entre a telemetria e a interface, e cada banco tem um papel diferente.


Três fluxos precisam funcionar e ser demonstrados:

IoT para Web: sensor simulado, MQTT, gateway, RabbitMQ, gravador no InfluxDB, API, WebSocket e dashboard.
Web para IoT: botão no dashboard, API, RabbitMQ, gateway, MQTT, simulador e atuador, que muda de estado e aparece nas leituras seguintes.
IA: o laboratório gera os dados sintéticos, o treino cria os modelos, a inferência os aplica à telemetria ao vivo e devolve previsões e alertas pelo RabbitMQ até a interface.
O InfluxDB guarda as leituras e a telemetria. O PostgreSQL guarda usuários, dispositivos, configurações, regras, alertas e auditoria.

Sensores, atuadores e equipamentos monitorados
O dispositivo é um simulador em software (Python) que publica a telemetria no Mosquitto e escuta os comandos vindos da aplicação. Os atuadores precisam reagir: ao receber um comando, o simulador muda o estado do atuador e isso aparece nas leituras seguintes (por exemplo, a bomba ligada faz a vazão subir).

O projeto deve ter:

pelo menos 3 sensores (temperatura, umidade, luminosidade, umidade do solo, nível de água, vazão, pressão, qualidade do ar, presença, corrente elétrica, consumo de energia, entre outros);
pelo menos 2 atuadores, sendo um acionado automaticamente por regra de negócio (por exemplo, temperatura acima de 35 °C liga o ventilador) e outro controlado pelo usuário na aplicação Web;
pelo menos 1 equipamento monitorado, ou seja, uma máquina que se desgasta e pode falhar (bomba, motor, ventilador, compressor, esteira). Ele deve ter no mínimo 3 variáveis medidas que mudem quando ele degrada, como vibração, corrente e temperatura. É ele que alimenta a IA de manutenção preditiva.
Exemplos de projetos AIoT (referência; o grupo pode propor outro, desde que cumpra todos os requisitos):

Projeto

Sensores

Atuadores

Equipamento monitorado e insights de IA

Smart Agriculture

Umidade do solo, temperatura, luminosidade, vazão

Irrigação, ventilação, iluminação

Bomba de irrigação: saúde e vida útil restante; previsão da umidade do solo

Monitoramento Industrial

Temperatura, vibração, corrente elétrica

Ventilação, sinalização, desligamento de equipamento

Motor ou compressor: saúde, tempo até a falha e consumo esperado

Reservatório Inteligente

Nível de água, vazão, pressão

Bomba, válvula

Bomba: desgaste e perda de eficiência; previsão do nível nas próximas horas

Estufa Inteligente

Temperatura, umidade, luminosidade

Irrigação, ventilação, iluminação

Ventilador: saúde; previsão da temperatura interna

Smart Campus

Temperatura, presença, qualidade do ar, consumo

Iluminação, ventilação, alertas

Ar-condicionado: saúde; previsão de consumo de energia por prédio

Smart Home

Presença, temperatura, luminosidade, corrente

Lâmpada, ventilador, alarme

Compressor da geladeira: saúde; previsão de consumo mensal


Interface 3D em tempo real
A aplicação deve ter uma página com um gêmeo digital 3D do ambiente do projeto (fazenda, fábrica, campus, reservatório), feito com Three.js ou equivalente na Web (TresJS, React Three Fiber, Babylon.js). Cenas simples, procedurais e de poucos polígonos são aceitas; a nota não depende de modelos sofisticados, e sim de a cena estar viva.

Regras da cena:

A cena muda somente com dados em tempo real, recebidos pelo WebSocket. Não pode haver ligação direta entre o simulador e o 3D. Se o simulador for desligado, a cena para e avisa que não há dados.
Todos os sensores, atuadores e o equipamento monitorado aparecem na cena. A posição 3D de cada um fica só no frontend, indexada pelo mesmo id do cadastro do dispositivo.
Cada item mostra seu estado por cor: normal, atenção, crítico ou sem dados. O estado vem da faixa normal do sensor e dos alertas da IA.
Os atuadores são animados quando ligados (ventilador girando, bomba vibrando, água saindo, lâmpada acesa). Quanto mais vibração o equipamento degradado tiver, mais ele deve tremer.
Pelo menos 2 elementos do ambiente reagem a dados reais, por exemplo dia e noite pela luminosidade, chuva pelo pluviômetro, nível de água do reservatório, fumaça ou fluxo pelas tubulações.
Ao clicar em um item, abre um painel com a última leitura, um mini gráfico, a saúde prevista pela IA e, para os atuadores controláveis, os botões de comando.
Se houver tubulações, cabos ou conexões, elas devem sair e chegar exatamente nos equipamentos, sem pontas soltas.
Boa prática de desempenho: não redesenhe a cena a cada mensagem. Guarde os dados em um store e leia-os dentro do loop de animação, e use instâncias (InstancedMesh) para repetições como plantação ou árvores.

Mensageria com RabbitMQ
Os dois brokers têm papéis diferentes e ambos são obrigatórios. O Mosquitto (MQTT) continua sendo o protocolo de borda, entre o dispositivo simulado e a aplicação. O RabbitMQ (AMQP) é o barramento interno: um gateway lê o MQTT e republica as mensagens no RabbitMQ, e dali cada serviço consome o que precisa.

Requisitos mínimos:

pelo menos 1 exchange do tipo topic, com routing keys que identifiquem o tipo e o dispositivo (por exemplo telemetry.<zona>.<tipo>.<id>);
pelo menos 4 filas com consumidores diferentes: gravação no InfluxDB, inferência da IA, entrega ao WebSocket e comandos de volta para o dispositivo;
filas para os jobs demorados (geração de dados e treino), para que a API não fique travada esperando;
uma fila de mensagens mortas (DLQ) para o que falhar, com a mensagem preservada;
mensagens em JSON com formato único (identificador, instante, tipo, dispositivo e conteúdo);
um usuário do RabbitMQ para cada serviço, com apenas as permissões de que ele precisa, e sem o usuário guest.
A aplicação deve ter uma página Mensageria que mostra ao vivo a quantidade de mensagens em cada fila, as taxas de publicação e de entrega, os consumidores conectados, as últimas mensagens e a DLQ. O backend consulta a API de gerenciamento do RabbitMQ; o navegador nunca fala direto com o broker.

Na apresentação, o grupo deve mostrar o efeito de um consumidor parado: a fila cresce enquanto ele está desligado e esvazia quando ele volta.

Dados sintéticos massivos
Equipamentos reais levam meses para falhar, então o grupo vai simular a vida inteira das máquinas para ter dados suficientes para treinar a IA. A aplicação deve ter uma página de Laboratório de Dados onde o usuário configura a geração e acompanha o progresso.

Parâmetros mínimos configuráveis na interface:

número de equipamentos e de sensores de cada tipo;
período simulado em dias;
percentual de equipamentos que vão falhar e os modos de falha (por exemplo desgaste de rolamento, entupimento, superaquecimento, desbalanceamento, deriva ou travamento de sensor);
nível de ruído, percentual de leituras faltantes e de valores absurdos (outliers);
semente aleatória, para que a geração seja reproduzível.
Regras de qualidade dos dados:

a degradação precisa ser progressiva: antes da falha, vibração, corrente e temperatura sobem aos poucos, com ruído e sobreposição entre máquinas saudáveis e doentes. Dado perfeito demais faz o modelo acertar 100% e não ensina nada;
o ciclo diário dos sensores (dia e noite, estações) deve existir nos dados;
cada leitura de treino tem os rótulos de verdade: se o equipamento estava degradando e quanto tempo faltava para falhar. Esses rótulos nunca podem ser enviados nas mensagens em tempo real, senão o modelo "cola" na prova;
o volume mínimo é de 1 milhão de leituras; o gerador deve usar numpy ou equivalente em blocos (não ponto a ponto) e ter um teto máximo para não travar a máquina;
o job roda em segundo plano, por fila do RabbitMQ, e a interface mostra o progresso. Uma amostra dos dados pode ser gravada em um bucket separado do InfluxDB (por exemplo lab), sem misturar com os dados ao vivo.
IA com regressão: manutenção preditiva e saúde dos equipamentos
O grupo deve treinar pelo menos 2 modelos de regressão com os dados sintéticos e usá-los em tempo real para gerar insights. São exemplos como:

Modelo de regressão

O que prevê (alvo contínuo)

Entradas típicas

Insight para o usuário

Vida útil restante (RUL)

Tempo até a falha, em horas

Vibração, corrente, temperatura e suas tendências

"A bomba 02 deve falhar em cerca de 18 h"

Índice de saúde

Nota de 0 a 100 do estado do equipamento

As mesmas janelas de leitura

Semáforo de saúde de cada máquina

Previsão de uma variável

Temperatura ou umidade do solo daqui a 1 h

Histórico recente e hora do dia

Acionar irrigação ou ventilação antes de passar do limite

Consumo de energia

Corrente ou kWh nas próximas horas

Histórico de consumo e carga

Previsão de consumo e desvio fora do esperado

Eficiência esperada

Vazão ou rendimento esperado

Pressão, corrente, rotação

Resíduo grande entre esperado e medido indica entupimento ou vazamento

Nível do reservatório

Tempo até esvaziar

Nível, vazão de saída, bomba ligada

Aviso antes de o nível ficar crítico

Leitura esperada de um sensor

Valor que o sensor deveria marcar

Sensores vizinhos

Resíduo alto indica sensor com deriva ou travado

Requisitos técnicos:

as variáveis de entrada (features) são calculadas por um único código, usado no treino e na inferência em tempo real, para não haver divergência entre os dois;
as janelas olham só para o passado (média, desvio, tendência, máximo); usar o futuro é vazamento de dados;
a divisão em treino, validação e teste é por equipamento, nunca aleatória por linha, porque linhas vizinhas da mesma máquina são quase iguais;
métricas de regressão na página de Treinamento: MAE, RMSE e R², gráfico de previsto contra real, importância dos atributos e comparação com uma base simples (por exemplo, prever sempre a média). O modelo só vale se vencer essa base;
o treino é disparado pela interface, roda em segundo plano e o modelo novo entra em uso sem reiniciar o serviço, mostrando a versão em uso;
a inferência roda em tempo real sobre a telemetria que chega pelo RabbitMQ e publica previsões e alertas de volta;
alertas usam limites com histerese (por exemplo, exigir 3 previsões seguidas abaixo do limite para disparar e 10 acima para limpar), para não ficar piscando.
A página Insights mostra, por equipamento, o índice de saúde, a vida útil restante, a tendência e os alertas ativos, e esses mesmos dados colorem os itens na cena 3D. Classificação (probabilidade de falha) pode complementar a regressão, mas não a substitui.

Assistente com LLM local
A aplicação deve ter uma página Assistente, um chat que responde perguntas em linguagem natural sobre os dados da solução. O LLM roda localmente, em container no Docker Compose, sem chave de API e sem enviar dado para a nuvem. Use um modelo pequeno que rode em CPU, por exemplo llama3.2:3b no Ollama; uma máquina com GPU não é necessária.

O que o assistente deve saber responder:

o estado atual: últimas leituras, equipamentos com pior saúde, alertas abertos;
as previsões da IA: vida útil restante, o que o alerta significa e o que fazer;
os modelos: métricas do último treino explicadas em palavras simples;
o contexto da solução: como os dados fluem pela arquitetura e por que cada tecnologia foi usada.
Como ligar o LLM aos dados:

o backend monta um resumo dos dados atuais (saúde, RUL, alertas, métricas do modelo) e o envia junto com a pergunta. Modelos pequenos erram ao chamar ferramentas, então o resumo vai pronto no prompt;
o LLM nunca acessa os bancos diretamente. Qualquer ferramenta oferecida a ele é somente leitura e está em uma lista fixa;
a resposta chega em streaming, palavra a palavra, e a interface mostra "carregando o modelo" enquanto ele sobe;
a saída do LLM é tratada como texto não confiável: renderizar Markdown sem HTML e sem imagens remotas;
há limite de perguntas por minuto por usuário, e cada pergunta é registrada no log de auditoria.
Com CPU, a primeira resposta demora porque o modelo precisa carregar na memória. Deixe o modelo pré-carregado ao subir o Compose para a demonstração não ficar esperando. Aumente a memória do Docker (no Windows, do WSL2) para pelo menos 8 GB.

Segurança, Docker Compose e GitHub
A solução inteira deve subir com um único comando (docker compose up), em qualquer máquina com Docker. Isso inclui frontend, API, gateway, simulador, Mosquitto, RabbitMQ, PostgreSQL, InfluxDB, os serviços de geração de dados, treino e inferência e o LLM local. Os serviços precisam ter verificação de saúde (healthcheck) e ordem de subida correta.

Segurança mínima exigida:

login com token JWT e três papéis: visualizador só vê, operador comanda atuadores e simulador, administrador também gera dados, treina modelos e vê a auditoria;
senhas guardadas com hash (bcrypt) e limite de tentativas de login;
nenhuma senha ou chave dentro do Git: segredos ficam em arquivos ignorados pelo .gitignore (por exemplo .env ou uma pasta secrets/), gerados por um script. Nada de usuário e senha padrão como admin/admin;
Mosquitto sem acesso anônimo, com usuário e permissões por tópico; RabbitMQ com usuário por serviço;
o WebSocket não recebe o JWT na URL (use um ticket curto, de uso único);
containers da aplicação sem rodar como root e só a porta do frontend publicada para a aplicação;
tabela de auditoria no PostgreSQL com logins, comandos enviados e jobs disparados.
Por ser um ambiente de aprendizado, as interfaces do InfluxDB, do RabbitMQ e do PostgreSQL (por exemplo com pgAdmin) podem ficar abertas, mas somente em 127.0.0.1, para o grupo explorar os dados durante a aula. Mostre os links dessas interfaces em uma página da aplicação.

No GitHub, o repositório deve ter o histórico de commits de todos os integrantes e um README com a descrição do projeto, o diagrama da arquitetura, como subir com Docker Compose, os usuários de demonstração (sem as senhas) e como rodar cada parte da demonstração.

Avaliação: 10,0 pontos
A pontuação de cada item depende do seu correto funcionamento durante a apresentação. A simples inclusão da tecnologia no código, sem demonstrar seu funcionamento, não garante a pontuação correspondente.

Critério

O que será observado

Pontos

Evolução e qualidade geral da aplicação

Evolução sobre o 1º bimestre, organização, segurança mínima e GitHub com README

1,0

Sensores, atuadores e MQTT + Mosquitto

Pelo menos 3 sensores e 2 atuadores, comunicação bidirecional funcionando

1,0

Regra automática e controle pela Web

Um atuador acionado por regra de negócio e outro comandado pelo dashboard

1,0

RabbitMQ

Exchange, filas, consumidores, DLQ e página Mensageria ao vivo

1,0

PostgreSQL e InfluxDB

Cada banco com papel correto, cadastro de dispositivos e consulta ao histórico

1,0

WebSocket, dashboard, gráficos e histórico

Atualização em tempo real, gráficos, indicadores e histórico das leituras

1,0

Interface 3D

Cena Three.js viva, movida só por dados em tempo real, com painel por item

1,0

Dados sintéticos e modelos de regressão

Gerador massivo configurável, 2 modelos treinados, métricas e comparação com a base simples

1,0

Insights de IA e LLM local

Saúde, RUL e alertas em tempo real; assistente local respondendo sobre os dados

1,0

Docker Compose e apresentação completa

Tudo sobe com um comando e a demonstração completa funciona

1,0

Total


10,0

Apresentação final
A apresentação será presencial, em sala de aula, no dia 16 de nov. de 2026. Não é necessário preparar slides: o grupo apresenta diretamente a aplicação funcionando. O objetivo é demonstrar que todas as tecnologias obrigatórias funcionam e estão integradas entre si.

Roteiro da demonstração, nesta ordem:

docker compose up subindo todos os serviços, com os containers saudáveis.
Login na interface Web e os três papéis de usuário.
Simulador enviando dados dos sensores e as mensagens passando pelo Mosquitto (MQTT).
Backend FastAPI, mostrando a documentação da API REST.
Página Mensageria com o RabbitMQ: filas, consumidores e o efeito de um consumidor parado.
Leituras no InfluxDB e dispositivos, regras e auditoria no PostgreSQL, com consulta ao histórico.
Dashboard atualizando em tempo real por WebSocket, com gráficos e indicadores.
Um atuador acionado automaticamente por regra de negócio e outro controlado pelo botão do dashboard (Web para IoT).
Laboratório de Dados gerando um volume massivo de leituras sintéticas.
Treinamento dos modelos de regressão e leitura das métricas.
Falha injetada em um equipamento, com saúde, vida útil restante e alerta mudando na página Insights e na cena 3D.
Assistente com LLM local respondendo perguntas sobre essa falha.
Todos os integrantes devem conhecer o funcionamento do projeto e poderão ser questionados sobre a arquitetura, os dados, a IA e as tecnologias utilizadas.
```
