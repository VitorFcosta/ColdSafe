# Tarefas AIoT

36 cartões do plano aprovado, sem replanejamento.
Status importados em 13/10/2026; cada cartão é o registro de execução.
Este índice resume os cartões e deve acompanhar futuras mudanças de status.
Ler só o cartão escolhido e suas dependências.
B2-01–25 concluídas nos seus escopos; B2-26–36 não iniciadas.
A migração documental não executou tarefas técnicas.

| Tarefa | Status atual | Dependências | Meta original |
| --- | --- | --- | --- |
| [B2-01 — Organizar Notion e matriz de requisitos](B2-01.md) | Concluída | Plano aprovado | 2026-10-12 |
| [B2-02 — Registrar baseline local e pendências](B2-02.md) | Concluída | B2-01 | 2026-10-12 a 2026-10-13 |
| [B2-03 — Validar capacidade do Mac de 8 GB](B2-03.md) | Concluída | B2-02 | 2026-10-13 a 2026-10-14 |
| [B2-04 — Fechar contratos de sensores, mensagens e previsões](B2-04.md) | Concluída | B2-02 | 2026-10-13 a 2026-10-14 |
| [B2-05 — Planejar e aplicar migrações de papéis, jobs e modelos](B2-05.md) | Concluída | B2-03, B2-04 | 2026-10-15 a 2026-10-16 |
| [B2-06 — JWT, bcrypt, limites de login e ticket WebSocket](B2-06.md) | Concluída | B2-05 | 2026-10-16 a 2026-10-17 |
| [B2-07 — RabbitMQ, credenciais, filas e DLQ](B2-07.md) | Concluída | B2-03, B2-04 | 2026-10-17 a 2026-10-18 |
| [B2-08 — Proxy do frontend, portas e bootstrap seguro](B2-08.md) | Concluída | B2-06, B2-07 | 2026-10-18 |
| [B2-09 — Simulador de sensores e degradação](B2-09.md) | Concluída | B2-04, B2-07 | 2026-10-19 a 2026-10-20 |
| [B2-10 — LED, buzzer e confirmações no simulador](B2-10.md) | Concluída | B2-09 | 2026-10-20 |
| [B2-11 — Gateway MQTT e AMQP bidirecional](B2-11.md) | Concluída | B2-07, B2-10 | 2026-10-21 |
| [B2-12 — Gravador de telemetria no InfluxDB](B2-12.md) | Concluída | B2-11 | 2026-10-21 a 2026-10-22 |
| [B2-13 — Consumidor da API, regras e WebSocket](B2-13.md) | Concluída | B2-06, B2-11, B2-12 | 2026-10-22 a 2026-10-23 |
| [B2-14 — Integrar dashboard e novos sensores](B2-14.md) | Concluída | B2-10, B2-13 | 2026-10-23 |
| [B2-15 — Painel de filas, taxas e consumidores](B2-15.md) | Concluída | B2-07, B2-13, B2-14 | 2026-10-24 |
| [B2-16 — Últimas mensagens, DLQ e consumidor parado](B2-16.md) | Concluída | B2-12, B2-15 | 2026-10-25 |
| [B2-17 — Jobs assíncronos, progresso e concorrência](B2-17.md) | Concluída | B2-05, B2-07, B2-13 | 2026-10-26 |
| [B2-18 — Gerador massivo em blocos](B2-18.md) | Concluída | B2-09, B2-17 | 2026-10-27 |
| [B2-19 — Laboratório de Dados e validação do dataset](B2-19.md) | Concluída | B2-18 | 2026-10-28 |
| [B2-20 — Features compartilhadas e divisão por equipamento](B2-20.md) | Concluída | B2-18, B2-19 | 2026-10-29 |
| [B2-21 — Baseline e regressão de saúde](B2-21.md) | Concluída | B2-20 | 2026-10-30 |
| [B2-22 — Baseline e regressão de vida útil restante](B2-22.md) | Concluída | B2-20, B2-21 | 2026-10-31 a 2026-11-01 |
| [B2-23 — Métricas, gráficos e importância no treinamento](B2-23.md) | Concluída | B2-21, B2-22 | 2026-11-01 a 2026-11-02 |
| [B2-24 — Versionar e ativar modelos](B2-24.md) | Concluída | B2-23 | 2026-11-02 |
| [B2-25 — Inferência ao vivo e troca de versão](B2-25.md) | Concluída | B2-13, B2-24 | 2026-11-03 |
| [B2-26 — Alertas com histerese e página Insights](B2-26.md) | Não iniciada | B2-25 | 2026-11-04 |
| [B2-27 — Cena 3D, IDs e estados](B2-27.md) | Não iniciada | B2-14, B2-26 | 2026-11-05 |
| [B2-28 — Animações, ambiente reativo e ausência de dados](B2-28.md) | Não iniciada | B2-27 | 2026-11-06 |
| [B2-29 — Painel por item e comandos autorizados no 3D](B2-29.md) | Não iniciada | B2-28 | 2026-11-07 |
| [B2-30 — Ollama, pré-carregamento e coordenação de memória](B2-30.md) | Não iniciada | B2-03, B2-17 | 2026-11-08 |
| [B2-31 — Resumo autorizado, streaming, limites e auditoria](B2-31.md) | Não iniciada | B2-06, B2-26, B2-30 | 2026-11-09 |
| [B2-32 — Página Assistente e avaliação das respostas](B2-32.md) | Não iniciada | B2-31 | 2026-11-10 |
| [B2-33 — Inicialização completa e recuperação](B2-33.md) | Não iniciada | B2-08, B2-16, B2-19, B2-24, B2-29, B2-32 | 2026-11-11 a 2026-11-12 |
| [B2-34 — Regressão, integração real, segurança e cobertura](B2-34.md) | Não iniciada | B2-33 | 2026-11-12 a 2026-11-13 |
| [B2-35 — README, diagramas e roteiro final](B2-35.md) | Não iniciada | B2-34 | 2026-11-14 |
| [B2-36 — Ensaiar demonstração e corrigir bloqueadores](B2-36.md) | Não iniciada | B2-35 | 2026-11-15 |
