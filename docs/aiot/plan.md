# Plano AIoT aprovado

Aprovado em 12/10/2026; migrado em 13/10. Este é o alvo da entrega,
não uma descrição de funcionalidades já implementadas. Estado: [tarefas](tasks/README.md).
O [guia](README.md) registra decisões gerais; os [requisitos](requirements.md)
guardam o aceite, e os [contratos](../../contracts/aiot.md) guardam formatos.

## Simulação e interface

O ventilador degrada por desgaste de rolamento/desbalanceamento, com ruído e
diferenças entre máquinas. Vibração, corrente e temperatura do motor variam;
a perda de eficiência afeta a temperatura ambiente. LED afeta luz, e o estado
do buzzer aparece na telemetria.

A cena Three.js lê a store alimentada pelo WebSocket. Representa equipamento,
todos os sensores e atuadores pelos IDs do cadastro; posições ficam no frontend.
Cores normal/atenção/crítico/sem dados, giro e tremor seguem dados recebidos.
Iluminação e indicador térmico são os dois elementos ambientais reativos.
Painel por item: leitura, mini gráfico, saúde/RUL quando aplicável e comando
autorizado. Sem conexão direta simulador→3D nem valores inventados.

Novas páginas: Mensageria, Laboratório, Treinamento, Insights, Gêmeo Digital e
Assistente. Reaproveitar navegação e componentes existentes.

## Dados, treino e modelos

- Laboratório configura equipamentos, sensores por tipo, dias, percentual e
  modos de falha, ruído, faltantes, outliers e seed.
- Gerar ≥1 milhão de leituras em blocos NumPy no disco. Teto inicial de 2 milhões
  condicionado à capacidade; ciclos diários e imperfeições. Labels só offline.
- Um módulo de features compartilhado entre treino/online, com janelas passadas.
  Separar por equipamento antes de ajustar transformações; tratar RUL censurado.
- Dois HistGradientBoostingRegressor separados: saúde 0–100 e RUL em horas.
  Comparar cada um a DummyRegressor; mostrar MAE/RMSE/R², previsto×real e
  importância por permutação.
- Promover apenas candidato aprovado na validação; registrar teste reservado
  sem usá-lo para ajustar escolhas. Artefatos internos confiáveis, versionados,
  com registro PostgreSQL e ativação atômica sem restart.
- Histerese inicial: 3 previsões críticas para abrir e 10 recuperadas para limpar,
  com limiares explícitos. Ausência de dados não fecha alerta.

## Serviços e memória

Fluxos e responsabilidades: [arquitetura](architecture.md). Formatos, comandos,
ACK, duplicatas, retry e indisponibilidade: [contrato v3](../../contracts/aiot.md).
Amostras de mensageria vêm de consumidor observador próprio, sem retirar mensagens
das filas de negócio.

O backend monta contexto autorizado para Ollama CPU. O modelo não acessa bancos
nem executa comandos. Streaming, carregamento, limite por usuário, auditoria e
saída como texto não executável.

Um job pesado por vez; descarregar LLM durante geração/treino, recarregar depois
e pré-carregar antes da apresentação. O plano partiu de llama3.2:1b; os perfis
efetivamente medidos e suas limitações estão na [B2-03](tasks/B2-03.md).
O ensaio não avaliou o assistente real nem consumidores de negócio.
B2-33 repete a medição na pilha completa; se não couber, registrar bloqueio
e rever a máquina, sem esconder serviços obrigatórios.

## Segurança e compatibilidade previstas

JWT com expiração/revogação, três papéis e propriedade em REST, WS, jobs,
modelos e chat. Registro público não escolhe administrador.
Bcrypt é exigido no enunciado; preservar verificação Argon2 e rehash após login,
sem apagar contas ou truncar senha. Rate limit no login e ticket WS curto,
único e sem JWT na URL.

Segredos gerados fora do Git; credenciais/ACL distintas, aplicações sem root,
frontend como entrada normal. Interfaces administrativas opcionais só em
127.0.0.1, com links na aplicação. Bootstrap idempotente, healthchecks e
volumes persistentes.

Dependências previstas: Three.js, cliente AMQP Python, NumPy, scikit-learn,
JWT, bcrypt e HTTP assíncrono; serviços RabbitMQ, Ollama e proxy/servidor estático.
Escolher/fixar versões na implementação; planejamento não significa instalação.

## Calendário original

| Meta | Tarefas / marco |
| --- | --- |
| 12–14/10 | B2-01–04: organização, baseline, capacidade e contratos |
| 15–18/10 | B2-05–08: dados, acesso e infraestrutura |
| 19–23/10 | B2-09–14: IoT↔Web |
| 24–28/10 | B2-15–19: mensageria e laboratório |
| 29/10–02/11 | B2-20–24: modelos avaliados |
| 03–07/11 | B2-25–29: inferência, insights e 3D |
| 08–10/11 | B2-30–32: assistente |
| 11–15/11 | B2-33–36: validação, documentação e ensaio |
| 16/11 | Apresentação presencial |

Datas individuais e dependências ficam nos cartões, sem recalcular o planejamento.

## Validação

Unitários, integração real e E2E de fluxos críticos; meta de 80% nas áreas medidas.
Cobrir acesso cruzado, JWT/ticket inválido, duplicatas, consumidor parado, DLQ,
reconexão/restart, persistência, censura, leakage, troca de modelo, cena stale e
assistente sem dados. API simulada não comprova brokers, bancos ou equipamento.

Fontes consultadas no planejamento: [split por grupos](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/cross_validation.rst),
[DLQ](https://www.rabbitmq.com/docs/dlx), [llama3.2](https://ollama.com/library/llama3.2),
[memória/carregamento Ollama](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).
