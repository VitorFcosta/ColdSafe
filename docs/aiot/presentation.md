# Apresentação final — 16/11/2026

Apresentação presencial em 2026-11-16, diretamente na aplicação. Sem necessidade de slides. **Nenhum passo abaixo foi validado nesta organização documental.**

## Preparação

- [ ] Todos os integrantes conhecem arquitetura, dados, IA e sua contribuição real.
- [ ] Imagens e modelo local já baixados; Ollama pré-carregado.
- [ ] Máquina final e orçamento de memória aprovados; evitar treino simultâneo ao assistente.
- [ ] Versão demonstrada identificada; segredos não aparecem na tela ou documentação.
- [ ] Contas de demonstração com três papéis e ambientes privados; senhas guardadas fora do Notion.
## Roteiro obrigatório, nesta ordem

1. Executar docker compose up e mostrar serviços saudáveis.
2. Fazer login e demonstrar visualizador, operador e administrador.
3. Mostrar simulador e telemetria pelo MQTT/Mosquitto.
4. Abrir documentação REST do FastAPI via entrada da aplicação.
5. Abrir Mensageria: filas/consumidores; parar gravador, ver fila crescer, retomar e ver esvaziar; mostrar DLQ.
6. Conferir leituras no InfluxDB e cadastros/regras/auditoria no PostgreSQL; consultar histórico.
7. Mostrar dashboard, gráficos e indicadores atualizando por WebSocket.
8. Provocar regra do buzzer e controlar LED pela Web, verificando ACK e leituras seguintes.
9. Gerar ≥1 milhão de leituras pelo Laboratório, mostrando parâmetros, seed e progresso.
10. Treinar saúde e RUL; mostrar MAE, RMSE, R², baseline, previsto×real e importância.
11. Injetar degradação no ventilador; observar saúde, RUL, tendência, alertas e cena 3D; mostrar painel e ausência de dados.
12. Perguntar ao assistente local sobre a falha, as métricas e a arquitetura.
## Perguntas para ensaiar

- Por que Mosquitto e RabbitMQ não são redundantes?
- Qual banco guarda cada tipo de dado?
- Como provar que um comando foi aplicado?
- Por que separar treino/teste por equipamento?
- Como evitar que a IA veja o futuro ou os rótulos?
- Por que modelos sintéticos não comprovam precisão em equipamento real?
- O que acontece sem modelo, sem leitura ou com consumidor parado?
- Como o 3D prova que está seguindo o sistema?
- Como os 8 GB são administrados e como os três papéis são testados?
## Registro de ensaio

Data/versão/máquina: pendente.
Resultado de cada passo: pendente.
Duração, bloqueios e evidências: pendentes.
Repetir ensaio após correções materiais. Apresentar limitações honestamente; não marcar requisito atendido só pela inclusão da biblioteca.
