# Requisitos e matriz de aceite

20 grupos de requisitos. A nota depende da demonstração integrada; conclusão documental e capacidade preliminar não equivalem ao aceite do software.

Fonte: [Enunciado do professor](../history/assignment.md).

| Requisito | O que cumprir | Como comprovar |
| --- | --- | --- |
| **R01 · Evolução e stack** | Mesmo problema; Vue 3 + TypeScript + Vite + Chart.js; FastAPI REST. Node só como ferramenta de frontend. | Navegar e explicar reaproveitamento da base. |
| **R02 · IoT bidirecional** | Simulador Python; ≥3 sensores, MQTT/Mosquitto nos dois sentidos; atuadores reagem e publicam o novo estado. | Comparar comando, ACK e leitura seguinte. |
| **R03 · Atuação automática e manual** | Buzzer por regra térmica com recuperação; LED pela Web; confirmação e auditoria. | Alterar temperatura e acionar LED no dashboard. |
| **R04 · Equipamento preditivo** | Ventilador com vibração, corrente e temperatura do motor; degradação progressiva afeta ambiente. | Injetar desgaste/desbalanceamento e observar as três variáveis. |
| **R05 · RabbitMQ e confiabilidade** | Exchange topic, routing keys por tipo/dispositivo, ≥4 filas/consumidores distintos, filas de jobs, DLQ preservada, JSON único e usuário por serviço sem guest. | Exibir topologia, filas e mensagem inválida na DLQ. |
| **R06 · Mensageria ao vivo** | Filas, taxas, consumidores, últimas mensagens e DLQ via backend/Management API; consumidor parado acumula e retoma. | Parar gravador e conferir crescimento/esvaziamento. |
| **R07 · Bancos e cadastros** | PostgreSQL: usuários, dispositivos, regras, alertas, auditoria e jobs/modelos. InfluxDB: leituras. CRUD e histórico preservados. | Salvar cadastro e consultar leitura persistida. |
| **R08 · WebSocket e dashboard** | Gráficos, indicadores e histórico ao vivo; estado de leitura desatualizada e reconexão. | Observar atualização sem recarregar e recuperar conexão. |
| **R09 · Laboratório massivo** | UI: equipamentos, sensores/tipo, dias, %falha, modos, ruído, faltantes, outliers, seed. ≥1 milhão de leituras em blocos; teto de volume; job em fila e progresso. | Disparar geração e conferir volume/configuração. |
| **R10 · Regressão e avaliação** | ≥2 regressores; saúde e RUL. Split por equipamento; MAE/RMSE/R², previsto×real, importância e baseline; modelos precisam vencê-la. | Comparar os dois modelos às baselines e explicar métricas. |
| **R11 · Inferência e integridade** | Features únicas treino/online, somente passado, sem labels em MQTT; versões trocam sem reinício; previsões voltam pelo RabbitMQ. | Ver versão mudar e conferir mensagem sem rótulo. |
| **R12 · Insights e histerese** | Saúde, RUL, tendência e alertas; abertura/recuperação com previsões consecutivas; sem dado não significa recuperação. | Provocar falha, oscilar no limiar e recuperar. |
| **R13 · 3D fiel aos dados** | Three.js; todos sensores/atuadores/equipamento; IDs do cadastro, posições só frontend; cores normal/atenção/crítico/sem dados; sem ligação simulador→3D. | Clicar itens e parar simulador: cena congela e avisa. |
| **R14 · 3D interativo e desempenho** | Atuadores animados, tremor proporcional à vibração, ≥2 elementos ambientais reativos, painel com leitura/mini gráfico/saúde/comandos; conexões sem pontas soltas; store e loop. | Demonstrar iluminação e térmica, painel e controle LED. |
| **R15 · LLM local** | Ollama CPU no Compose, modelo pequeno, sem nuvem/chave; estado atual, previsões, métricas e arquitetura; resumo pronto pelo backend. | Perguntar sobre falha e comparar resposta aos dados. |
| **R16 · Chat seguro** | LLM sem banco direto; streaming, carregamento, saída não confiável sem HTML/imagens remotas, rate limit por usuário e auditoria. | Testar carregamento, limite e pergunta registrada. |
| **R17 · Capacidade e inicialização LLM** | Pré-carregar para demonstração; memória medida. Mac 8 GB é risco, pois enunciado recomenda ≥8 GB ao Docker. | Registrar RAM, latência, ausência de OOM e coordenação de jobs. |
| **R18 · Segurança e isolamento** | JWT, 3 papéis, bcrypt, limite login, segredos gerados fora Git, ACL Mosquitto, usuário RabbitMQ/serviço, ticket WS único, containers app sem root, auditoria e contas privadas. | Testar permissões e acesso cruzado; conferir auditoria. |
| **R19 · Compose e interfaces locais** | Tudo no Compose com docker compose up, healthchecks/ordem, somente porta frontend; UIs administrativas opcionais em 127.0.0.1 com links na aplicação. | Subida completa e reinício preservando dados. |
| **R20 · GitHub e apresentação** | Histórico real dos integrantes, README com arquitetura/subida/usuários sem senha/demos; apresentação 16/11 na ordem do professor; todos conhecem sistema. | Conferir versão e ensaio integral. |

## Avaliação do professor — 10 pontos

Cada bloco vale 1 ponto: evolução/qualidade; sensores/atuadores/MQTT; regra e controle Web; RabbitMQ; bancos; WebSocket/dashboard/histórico; 3D; dados sintéticos/regressão; insights/LLM; Compose/apresentação.
## Regras de evidência

- Vincular teste ou ensaio com data, versão, resultado e limitação.
- Aprovação da documentação B2-01 não comprova requisitos de software.
- Testes unitários, integração e E2E têm escopos diferentes; API simulada não comprova brokers/bancos.
- Exibir limitações de modelos sintéticos e capacidade de RAM medida; nunca copiar resultado antigo como teste atual.
