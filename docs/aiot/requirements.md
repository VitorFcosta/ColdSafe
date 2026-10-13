# Requisitos e matriz de aceite

20 grupos de requisitos. A nota depende da demonstração integrada; conclusão documental e capacidade preliminar não equivalem ao aceite do software.

Fonte: [📎 Enunciado original — requisitos do professor](../history/assignment.md). Plano: [📋 Plano técnico e cronograma — AIoT](plan.md).

| Requisito | O que cumprir | Tarefas | Como comprovar |
| --- | --- | --- | --- |
| **R01 · Evolução e stack** | Mesmo problema; Vue 3 + TypeScript + Vite + Chart.js; FastAPI REST. Node só como ferramenta de frontend. | [B2-02](tasks/B2-02.md) · [B2-04](tasks/B2-04.md) · [B2-14](tasks/B2-14.md) · [B2-34](tasks/B2-34.md) · [B2-35](tasks/B2-35.md) | Navegar e explicar reaproveitamento da base. |
| **R02 · IoT bidirecional** | Simulador Python; ≥3 sensores, MQTT/Mosquitto nos dois sentidos; atuadores reagem e publicam o novo estado. | [B2-09](tasks/B2-09.md) · [B2-10](tasks/B2-10.md) · [B2-11](tasks/B2-11.md) · [B2-14](tasks/B2-14.md) | Comparar comando, ACK e leitura seguinte. |
| **R03 · Atuação automática e manual** | Buzzer por regra térmica com recuperação; LED pela Web; confirmação e auditoria. | [B2-10](tasks/B2-10.md) · [B2-13](tasks/B2-13.md) · [B2-14](tasks/B2-14.md) · [B2-29](tasks/B2-29.md) | Alterar temperatura e acionar LED no dashboard. |
| **R04 · Equipamento preditivo** | Ventilador com vibração, corrente e temperatura do motor; degradação progressiva afeta ambiente. | [B2-09](tasks/B2-09.md) · [B2-25](tasks/B2-25.md) · [B2-26](tasks/B2-26.md) | Injetar desgaste/desbalanceamento e observar as três variáveis. |
| **R05 · RabbitMQ e confiabilidade** | Exchange topic, routing keys por tipo/dispositivo, ≥4 filas/consumidores distintos, filas de jobs, DLQ preservada, JSON único e usuário por serviço sem guest. | [B2-04](tasks/B2-04.md) · [B2-07](tasks/B2-07.md) · [B2-11](tasks/B2-11.md) · [B2-12](tasks/B2-12.md) · [B2-13](tasks/B2-13.md) · [B2-17](tasks/B2-17.md) | Exibir topologia, filas e mensagem inválida na DLQ. |
| **R06 · Mensageria ao vivo** | Filas, taxas, consumidores, últimas mensagens e DLQ via backend/Management API; consumidor parado acumula e retoma. | [B2-15](tasks/B2-15.md) · [B2-16](tasks/B2-16.md) | Parar gravador e conferir crescimento/esvaziamento. |
| **R07 · Bancos e cadastros** | PostgreSQL: usuários, dispositivos, regras, alertas, auditoria e jobs/modelos. InfluxDB: leituras. CRUD e histórico preservados. | [B2-05](tasks/B2-05.md) · [B2-12](tasks/B2-12.md) · [B2-14](tasks/B2-14.md) | Salvar cadastro e consultar leitura persistida. |
| **R08 · WebSocket e dashboard** | Gráficos, indicadores e histórico ao vivo; estado de leitura desatualizada e reconexão. | [B2-13](tasks/B2-13.md) · [B2-14](tasks/B2-14.md) | Observar atualização sem recarregar e recuperar conexão. |
| **R09 · Laboratório massivo** | UI: equipamentos, sensores/tipo, dias, %falha, modos, ruído, faltantes, outliers, seed. ≥1 milhão de leituras em blocos; teto de volume; job em fila e progresso. | [B2-17](tasks/B2-17.md) · [B2-18](tasks/B2-18.md) · [B2-19](tasks/B2-19.md) | Disparar geração e conferir volume/configuração. |
| **R10 · Regressão e avaliação** | ≥2 regressores; saúde e RUL. Split por equipamento; MAE/RMSE/R², previsto×real, importância e baseline; modelos precisam vencê-la. | [B2-20](tasks/B2-20.md) · [B2-21](tasks/B2-21.md) · [B2-22](tasks/B2-22.md) · [B2-23](tasks/B2-23.md) · [B2-24](tasks/B2-24.md) | Comparar os dois modelos às baselines e explicar métricas. |
| **R11 · Inferência e integridade** | Features únicas treino/online, somente passado, sem labels em MQTT; versões trocam sem reinício; previsões voltam pelo RabbitMQ. | [B2-04](tasks/B2-04.md) · [B2-20](tasks/B2-20.md) · [B2-24](tasks/B2-24.md) · [B2-25](tasks/B2-25.md) | Ver versão mudar e conferir mensagem sem rótulo. |
| **R12 · Insights e histerese** | Saúde, RUL, tendência e alertas; abertura/recuperação com previsões consecutivas; sem dado não significa recuperação. | [B2-25](tasks/B2-25.md) · [B2-26](tasks/B2-26.md) | Provocar falha, oscilar no limiar e recuperar. |
| **R13 · 3D fiel aos dados** | Three.js; todos sensores/atuadores/equipamento; IDs do cadastro, posições só frontend; cores normal/atenção/crítico/sem dados; sem ligação simulador→3D. | [B2-27](tasks/B2-27.md) · [B2-28](tasks/B2-28.md) · [B2-29](tasks/B2-29.md) | Clicar itens e parar simulador: cena congela e avisa. |
| **R14 · 3D interativo e desempenho** | Atuadores animados, tremor proporcional à vibração, ≥2 elementos ambientais reativos, painel com leitura/mini gráfico/saúde/comandos; conexões sem pontas soltas; store e loop. | [B2-27](tasks/B2-27.md) · [B2-28](tasks/B2-28.md) · [B2-29](tasks/B2-29.md) | Demonstrar iluminação e térmica, painel e controle LED. |
| **R15 · LLM local** | Ollama CPU no Compose, modelo pequeno, sem nuvem/chave; estado atual, previsões, métricas e arquitetura; resumo pronto pelo backend. | [B2-30](tasks/B2-30.md) · [B2-31](tasks/B2-31.md) · [B2-32](tasks/B2-32.md) | Perguntar sobre falha e comparar resposta aos dados. |
| **R16 · Chat seguro** | LLM sem banco direto; streaming, carregamento, saída não confiável sem HTML/imagens remotas, rate limit por usuário e auditoria. | [B2-31](tasks/B2-31.md) · [B2-32](tasks/B2-32.md) | Testar carregamento, limite e pergunta registrada. |
| **R17 · Capacidade e inicialização LLM** | Pré-carregar para demonstração; memória medida. Mac 8 GB é risco, pois enunciado recomenda ≥8 GB ao Docker. | [B2-03](tasks/B2-03.md) · [B2-17](tasks/B2-17.md) · [B2-30](tasks/B2-30.md) · [B2-33](tasks/B2-33.md) | Registrar RAM, latência, ausência de OOM e coordenação de jobs. |
| **R18 · Segurança e isolamento** | JWT, 3 papéis, bcrypt, limite login, segredos gerados fora Git, ACL Mosquitto, usuário RabbitMQ/serviço, ticket WS único, containers app sem root, auditoria e contas privadas. | [B2-05](tasks/B2-05.md) · [B2-06](tasks/B2-06.md) · [B2-07](tasks/B2-07.md) · [B2-08](tasks/B2-08.md) · [B2-17](tasks/B2-17.md) · [B2-31](tasks/B2-31.md) · [B2-34](tasks/B2-34.md) | Testar permissões e acesso cruzado; conferir auditoria. |
| **R19 · Compose e interfaces locais** | Tudo no Compose com docker compose up, healthchecks/ordem, somente porta frontend; UIs administrativas opcionais em 127.0.0.1 com links na aplicação. | [B2-03](tasks/B2-03.md) · [B2-08](tasks/B2-08.md) · [B2-30](tasks/B2-30.md) · [B2-33](tasks/B2-33.md) · [B2-35](tasks/B2-35.md) | Subida completa e reinício preservando dados. |
| **R20 · GitHub e apresentação** | Histórico real dos integrantes, README com arquitetura/subida/usuários sem senha/demos; apresentação 16/11 na ordem do professor; todos conhecem sistema. | [B2-01](tasks/B2-01.md) · [B2-02](tasks/B2-02.md) · [B2-35](tasks/B2-35.md) · [B2-36](tasks/B2-36.md) | Conferir versão e ensaio integral. |

## Avaliação do professor — 10 pontos

Cada bloco vale 1 ponto: evolução/qualidade; sensores/atuadores/MQTT; regra e controle Web; RabbitMQ; bancos; WebSocket/dashboard/histórico; 3D; dados sintéticos/regressão; insights/LLM; Compose/apresentação.
## Regras de evidência

- Vincular teste ou ensaio com data, versão, resultado e limitação.
- Aprovação da documentação B2-01 não comprova requisitos de software.
- Testes unitários, integração e E2E têm escopos diferentes; API simulada não comprova brokers/bancos.
- Exibir limitações de modelos sintéticos e capacidade de RAM medida; nunca copiar resultado antigo como teste atual.
