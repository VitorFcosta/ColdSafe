# Retomar a evolução AIoT

## Situação em 23/10/2026

O código continua na base v1/v2 descrita no [README](../../README.md).
O contrato v3 foi fechado; migrações 004–006 e metadados privados estão preparados.
O simulador MQTT v3, gateway MQTT/AMQP e gravador InfluxDB estão implementados;
API, regras de temperatura e entrega WebSocket v3 estão implementadas na B2-13;
dashboard v3 está integrado na B2-14; demais consumidores continuam posteriores.
O [índice de tarefas](tasks/README.md) e cada cartão são o registro de execução.

A [B2-32](tasks/B2-32.md) conserva página Assistente e aceite
factual aprovados. Após falhas preservadas no histórico, a rodada final com
Llama 3.2 3B Q4, quatro threads, lote 128 e 3,25 GiB/4 CPUs aprovou 14 perguntas e dois
extras mistos por revisão principal/independente. Serviço/SSE/SQL/Ollama CPU reais,
com fixtures declaradas; 16 auditorias concluídas e zero comandos. Regressão:
237 testes backend (96,14% nos cinco módulos alterados), 66 frontend, sete cenários
Chromium com HTTP simulado, percurso JWT/HTTP/SSE/SQL/Chromium com Ollama simulado
e build AIoT passaram. Os dois percursos são evidências distintas. Pesos 3B são a
nova dependência de infraestrutura; sem biblioteca Python/Node nova ou ativação
pessoal. Recursos descartáveis e credenciais foram removidos. Ressalvas de
linguagem, ensaios reprovados e limites ficam no cartão e na
[evidência final](../evidence/b2-32-final-2026-10-22.json).

A última tarefa concluída é a [B2-33](tasks/B2-33.md): healthchecks dos
executores, bootstrap InfluxDB idempotente e runbook completo. R5 aprovou a pilha
real com 14 serviços saudáveis, sete páginas, recuperação de writer/brokers/Ollama,
geração e treino de 1 milhão, ativação e `down/up` preservando dados/modelo/sessão.
Foram 1.058 amostras, sem OOM; treino atingiu o teto de 1 GiB. Quatro SSE completas
responderam corretamente à pergunta sobre equipamentos em 32–43 s. R3/R4 continuam
reprovadas: uma confirmou timeout de 92 s numa pergunta válida sobre ambientes,
ainda sem causa isolada/correção. R5 é smoke factual mais restrito de recuperação,
não nova aprovação do corpus B2-32 ou SLA. Testes focados: 512 aprovações/90,20%
nos oito módulos medidos; grupo bootstrap/segredos: 43 aprovações, com sobreposição.
Sem dependências novas, commit/push ou ativação pessoal; recursos próprios removidos.
[Evidência consolidada](../evidence/b2-33.json) e cartão registram limites e hashes.
B2-34 permanece não iniciada; aguardar escolha do usuário.

A [B2-31](tasks/B2-31.md): resumo privado somente leitura,
SSE autenticado, cinco admissões/minuto/conta, pergunta até 256 bytes UTF-8,
timeout/cancelamento, revalidação de sessão e auditoria persistente. Lock dos
jobs e marcador durável protegem geração/descarga. Backend sem integração:
1.454 aprovações; 79 testes novos passaram e a rodada final API/contratos teve
324 aprovações, cobertura combinada 86,18%. Grupos se sobrepõem. Ollama CPU real
respondeu três casos de dados preparados, com recusa de acesso cruzado/LED,
ausência de medidas para conta vazia, zero comandos e três auditorias. HTTP/SSE
e desconexão também foram ensaiados em sockets reais com upstream controlado.
HTTPX/HTTPcore foram promovidos do desenvolvimento ao runtime nas mesmas versões.
Sem ativação pessoal; margem de memória pequena e qualidade geral da linguagem
ainda não avaliada. A página Assistente foi entregue na B2-32. Limites, falha inicial
do Docker/recuperação e hashes em [evidência B2-31](../evidence/b2-31.json).

A [B2-30](tasks/B2-30.md) conserva Ollama local em CPU, Llama 3.2
1B Q4/contexto 1.024, pesos persistentes com preparo separado e runtime sem
saída à internet. Coordenador e jobs compartilham lock PostgreSQL; marcador
durável protege falha durante preload. Estado privado HTTP e avisos no
Laboratório/Treinamento explicam a pausa. 1.524 testes backend (92,21% de
cobertura), 420 frontend e quatro cenários Chromium com HTTP simulado passaram;
ensaio real descartável comprovou geração/treino de 1 milhão, descarga, recarga
automática, reinício e indisponibilidade. Worker atingiu o teto de 1 GiB sem OOM;
capacidade final continua B2-33. Falha ambígua de carga exige recuperação manual
segura. Sem biblioteca Python/Node nova ou ativação pessoal; imagem Ollama e pesos
são as dependências de infraestrutura. Detalhes/limites no cartão e nas
[evidências](../evidence/b2-30.json).

A [B2-29](tasks/B2-29.md) conserva painel por item com última
leitura, idade e gráfico por ID; saúde/RUL próprias dos sensores/atuadores não
aplicáveis, separadas da previsão do equipamento associado. Dashboard e gêmeo
reutilizam controle LED/ACK e permissões. 408 testes frontend, seis cenários
Chromium com HTTP/WS simulados e seis no percurso real descartável passaram;
POST real foi recusado após revogar papel no banco e outra conta permaneceu isolada.
Sem dependências novas, endpoints novos ou implantação pessoal. Histórico próprio
de estado dos atuadores não existe; o gráfico contextual é identificado. Detalhes,
limites e checkpoint no cartão e na [evidência](../evidence/b2-29.json).

A [B2-28](tasks/B2-28.md) conserva giro/tremor do ventilador,
brilho do LED e pulso visual do buzzer por telemetria; luz ambiente e barra térmica
reativas. Loop reutiliza os objetos, congela após freshness de 30 s mesmo com
WebSocket aberto e retoma por dados novos; preferência de movimento reduzido e
aba oculta suspendem animações. 395 testes frontend, quatro cenários Chromium
com HTTP/WS simulados e cinco cenários no percurso real descartável passaram.
Corrigida corrida de `.erlang.cookie`: healthcheck usa o mesmo usuário do broker.
Nenhuma dependência nova ou implantação pessoal. Escalas de movimento/temperatura
são ilustrativas; não houve calibração física nem ensaio de capacidade final.
Detalhes, limites e checkpoint no cartão e na [evidência](../evidence/b2-28.json).

A [B2-27](tasks/B2-27.md) conserva Gêmeo digital com Three.js direto
no Vue, seis sensores, LED, buzzer e ventilador ligados ao monitoramento WS/REST.
Inventário autorizado conserva nove IDs mesmo sem leitura; posições são locais
ao frontend. Clique/teclado compartilham seleção, valores e estados; falha WebGL
mantém lista acessível. Chromium/WebGL reais comprovaram raycast, 320 px,
troca de ambiente/resposta antiga e descarte de contextos após navegação;
HTTP/WS do ensaio original são fixtures declaradas. Adicionados Three.js/tipos
com versões fixadas, sem atualizar pacotes anteriores. A ativação pessoal foi
autorizada e executada em 20/10: catálogo do `sim-lab-01` no ambiente Hospital 1,
overlays AIoT/jobs/inferência e serviços atualizados; seis sensores e recibo de
persistência reais no percurso do simulador foram conferidos. Em seguida, a
operação pessoal de geração de 1 milhão/treino/ativação foi concluída: modelo
`training-4ec768f5-b77d-4059-b27b-020b979fa066` ativo e saúde/RUL confirmadas no
Insights para Hospital 1 / Ventilador. Nenhuma dependência nova nessa operação.
Métricas e limites em [B2-23](tasks/B2-23.md), ativação em [B2-24](tasks/B2-24.md) e
percurso live em [B2-25](tasks/B2-25.md);
[evidência datada](../evidence/personal-training-2026-10-20.json). Dados sintéticos,
RUL perto da falha ainda imprecisa e capacidade final não comprovada. Os parágrafos
seguintes conservam o escopo original das entregas, antes dessa operação pessoal.

A [B2-26](tasks/B2-26.md) conserva alertas preditivos persistentes com
regras privadas por proprietário, histerese inicial 3/10 e auditoria transacional;
página Insights exibe saúde/RUL, tendência, versão, idade e alertas. Ausência,
indisponibilidade, stale e troca de modelo interrompem sequências sem fechar
alerta. PostgreSQL/RabbitMQ/HTTP/Chromium reais comprovaram oscilação, reentrega,
interrupção de 31 s, recarga/recriação do serviço, recuperação e duas contas;
previsões/fonte/recibos são fixtures declaradas, sem ensaio físico ou InfluxDB.
Nenhuma dependência nova ou implantação pessoal; limites/testes no cartão.

A [B2-25](tasks/B2-25.md) conserva inferência de saúde/RUL ligada ao
barramento e dashboard, com restauração do ativo e troca sem reiniciar worker
ou navegador. Histórico/saída canônica são transacionais no PostgreSQL; kernel e
transformação do treino, fonte/versão e estados de indisponibilidade preservados.
PostgreSQL/RabbitMQ/API/WS/Chromium reais comprovaram troca A→B e falha mantendo B;
fonte/recibos são fixtures declaradas, sem novo ensaio InfluxDB ou calibração.
Paridade SQL/offline de uma hora passou; padrão continua 900/3600 s, sem encurtar
warm-up. Sem dependências novas ou implantação pessoal. Limites/testes no cartão.

A [B2-24](tasks/B2-24.md) conserva registro privado de versões e
ativação administrativa assíncrona, com validação/carga dos dois modelos antes
da troca atômica. Outbox e fila dedicada preservam pedidos/status; falha mantém
versão anterior e erro consultável. PostgreSQL/RabbitMQ reais comprovaram troca,
recuperação, retomada de `loading`, duplicatas, isolamento e rollback transacional.
Schema aceita o `+` já produzido em `features_version`; artefatos antigos intactos.
Sem dependências novas ou ativação no ambiente pessoal. Inferência/reidratação
do consumidor de previsões foram integradas na B2-25; limites no cartão respectivo.

A [B2-23](tasks/B2-23.md) conserva página Treinamento com jobs reais,
progresso recuperável, baseline/MAE/RMSE/R², dispersão e erros dos dois alvos,
importância por permutação em até 500 linhas reservadas e versões/seed/split.
PostgreSQL/RabbitMQ/Chromium reais comprovaram 1m, recarga sem reenvio, isolamento,
403 sem papel e valores iguais aos artefatos. Pacote privado registrado em
`models` para concluir o job, com **zero ativações**. Sem dependências novas.
Cobertura/testes e limite móvel stale já presente no dashboard estão no cartão.
Overlay pessoal não ativado; capacidade integral/física não foi comprovada.

A [B2-22](tasks/B2-22.md) conserva regressor independente de RUL em
horas, ajustado somente em falhas observadas, sem converter censurados em zero.
Saúde/RUL treinados em filhos separados e sequenciais no mesmo preparo de 1m;
ambos aptos pela validação, com modelos/métricas idênticos na repetição e fontes
intactas. RUL: MAE 57,44 h na validação e 40,55 h no teste, contra 149,99/144,38 h
do baseline. Nas últimas 24 h, MAE do teste ainda 14,00 h e R² negativo: limite
importante, sem comprovar precisão operacional ou calibração física. RUL final
22,01 s/580,17 MiB; sem dependências novas. Essas funções offline não registram/ativam;
a integração AMQP/resultados passou a existir na B2-23.

A [B2-21](tasks/B2-21.md) conserva regressão de saúde offline com
DummyRegressor e HistGradientBoostingRegressor; ajuste só no treino e escolha/gate
por MAE da validação, antes de abrir o teste reservado. Fonte de 1 milhão gerou
MAE 1,89 na validação e 2,46 no teste, contra 23,28/21,63 do baseline. Repetição
em processo novo confirmou métricas e bytes do modelo idênticos; treino final
33,9 s, pico RSS 573,9 MiB. scikit-learn e cinco transitivas adicionados aos locks,
sem atualizar versões existentes. Evidência sintética, sem validação física ou
ativação pessoal; integração AMQP do pacote saúde + RUL implementada na B2-23.

A [B2-20](tasks/B2-20.md) conserva kernel causal único e adaptadores
offline/online, preparação NPY por equipamento e split 70/15/15 sem máquinas
compartilhadas. Mediana/clipping ajustados apenas no treino, labels/censura
separados de X. Fontes reais de 1–2m comprovaram paridade online e integridade;
preparo medido ficou em 184/277 MiB após limitar mapas/fit a blocos/colunas.
Sem modelos, consumidor de inferência, dependências novas ou ativação pessoal.
Custos dependem da densidade das janelas; medidas não representam a pilha final.

A [B2-19](tasks/B2-19.md) conserva Laboratório Web para geração privada,
acompanhamento recuperável por UUID, configuração/autor e qualidade observada,
com amostra separada de dez linhas. Chromium/HTTP/PostgreSQL/RabbitMQ reais
comprovaram geração de um milhão, recarga sem reenvio, isolamento e falha parcial
sem dataset concluído. Resumo/amostra verificam todos os blocos por consulta;
há custo de I/O proporcional ao volume. Sem nova dependência ou ativação pessoal.

A [B2-18](tasks/B2-18.md) conserva gerador NumPy offline em blocos
de 50 mil, integrado ao worker de jobs e volume persistente privado. Foram
verificadas 1–2 milhões de linhas, reprodução por seed/hash, ruído/faltantes/
outliers, degradação e RUL censurada sem labels no live. Pico RSS medido:
82–89 MiB no Mac e 91,4 MiB no container no teto, sem extrapolar à pilha final.
Retomada repete deterministicamente em diretório exclusivo por tentativa;
órfãos exigem limpeza manual. Overlay pessoal não ativado. Detalhes/testes no cartão.

A [B2-17](tasks/B2-17.md) conserva infraestrutura de jobs privados,
POST administrativo `202`, outbox AMQP, workers com lock PostgreSQL único,
checkpoints/retomada e progresso HTTP/SSE autenticado por dono. PostgreSQL/RabbitMQ
reais e executores pequenos comprovaram assincronia, isolamento, concorrência,
duplicatas e retomada; geração massiva usa B2-18 e treino integrado usa B2-23.
Na B2-17, treino sem handler real terminava failed explicitamente. Overlay pessoal não ativado. Exclusão
depende da sessão PostgreSQL viva; ver limites de coordenação/recuperação no cartão.

A [B2-16](tasks/B2-16.md) conserva observador em fila dedicada e resumos
privados de últimas mensagens/DLQ na Mensageria. API valida o proprietário atual
no PostgreSQL; leitura não retira originais das filas de negócio/DLQ. Ensaio real
e Chromium passaram com backlog durante parada, esvaziamento na retomada,
persistência exata, mensagem inválida preservada e isolamento de contas.
Amostras são limitadas/em memória; não importam itens antigos da DLQ. Parada/retomada
seguem manuais no terminal. A ativação pessoal desta entrega não foi executada.

A [B2-15](tasks/B2-15.md) conserva nove filas e métricas globais administrativas
via API ColdSafe, usando credencial exclusiva de monitoramento.
`consumers` conta assinaturas do broker; serviços por polling podem mostrar zero
mesmo funcionando. A ativação local foi autorizada e concluída depois da entrega:
credenciais ausentes preenchidas, conta existente admin e serviços atualizados
com `compose.messaging.yaml`, preservando o dashboard e volumes. Detalhes no cartão.

A B2-14 conserva dashboard com seis medições, gráfico/tabela por grandeza,
histórico/recuperação REST v3, LED com confirmação separada do estado observado
e buzzer automático. Seu percurso real do simulador a 1 Hz permanece evidência
datada no cartão; não foi reexecutado como parte do aceite B2-15.

A B2-12 conserva gravador que consome fila própria e grava
seis sensores, IDs e estados no InfluxDB antes de confirmar. Identidade estável
preserva um ponto no redelivery/restart; histórico v1/v2 permanece no bucket legado.
Live usa `telemetry_live` e token exclusivo write-only; sintéticos ficam separados.
Integração final: seis casos reais aprovados, incluindo acúmulo/retomada, duplicatas,
legado, permissões e queda do InfluxDB com três tentativas/DLQ/recuperação.
Operação, campos e custo de cardinalidade estão no [writer](../../writer/README.md).
Gateway B2-11 conserva diário SQLite de aproximadamente 64 MiB sem expurgo;
operação em [gateway](../../gateway/README.md).
Sensores/atuadores/equipamento continuam no catálogo privado de comissionamento;
dispositivo/ambiente/proprietário são verificados no PostgreSQL. Estado/cache do
simulador ainda são em memória. A B2-13 isola status/timeout v3 do legado e
mantém o catálogo comissionado de um equipamento por runtime. A B2-09 conserva
sensores/desgaste; B2-08, frontend estático/proxy. A integração do dashboard
v3 está concluída no escopo B2-14. O cartão atual é [B2-33](tasks/B2-33.md);
não avançar automaticamente.

A capacidade preliminar foi medida na [B2-03](tasks/B2-03.md). O ensaio final
com os 14 serviços foi concluído na [B2-33](tasks/B2-33.md), no cenário e limites
descritos no cartão; isso não promete capacidade para qualquer carga.

## Decisões preservadas

- Ventilador de refrigeração; LED manual, buzzer automático, ambientes privados.
- Reaproveitar Vue 3/TypeScript/Vite/Chart.js, Python/FastAPI e os dois bancos;
  Three.js direto para a cena futura. Node serve ao frontend.
- Firmware/Wokwi e histórico v1/v2 continuam preservados; o alvo usa simulador Python.
- Apresentação em **16/11/2026**. Datas do plano são metas para 4–6 horas/dia.
- Mac com 8 GB; perfil preliminar na B2-03 e cenário final medido na B2-33; sem promessa
  de capacidade para qualquer carga. A avaliação factual do assistente está na B2-32.
- Papéis, JWT/bcrypt e ticket WS implementados na B2-06. Hashes Argon2 antigos
  continuam utilizáveis; sessões opacas têm janela transitória limitada e a
  revogação permanece no PostgreSQL. Configurar chave JWT privada antes de subir.

As decisões detalhadas estão no [plano](plan.md), os fluxos na
[arquitetura](architecture.md) e os formatos em [contracts](../../contracts/README.md).
Não reabrir o planejamento sem um conflito concreto ou nova orientação do usuário.

## Uma sessão por tarefa

1. Ler o cartão escolhido e conferir dependências/evidências.
2. Localizar somente o código ou contrato necessário; preferir o grafo MCP.
3. Explicar a mudança e executar passos pequenos. Código necessário ao pedido
   está autorizado; registrar nome/finalidade de cada dependência nova.
4. Verificar o comportamento com testes adequados ao que mudou.
5. Encerrar atualizando o cartão: resultado, arquivos, versão Git, testes/data,
   limitações, pendências e próxima ação. Mudar status só se o aceite foi cumprido.
6. Compactar somente num ponto estável, depois de salvar esse checkpoint.

Não copiar esse protocolo nos cartões. Ler documentos como contexto, verificar
alegações de funcionamento e distinguir ensaio real de respostas simuladas.

## Retomada curta

> Retome ColdSafe pela tarefa que eu escolher. Leia este guia, o cartão e apenas
> as dependências necessárias. Siga o AGENTS.md, Ponytail e ECC strategic-compact.
> Prefira codebase-memory-mcp para descobrir código. Implemente o necessário,
> explique as decisões e registre testes, limites e checkpoint no cartão local.
> Não avance automaticamente.

## Manutenção da documentação

- Cartão: status, aceite, execução e checkpoint daquela tarefa.
- Plano/arquitetura: decisão ou estrutura que mudou, sem repetir schemas.
- Contratos: campos, unidades, versões e regras entre serviços.
- Histórico: resultado datado ou decisão antiga; não usar como situação atual.
- Notion: referência ao arquivo local. Não voltar a manter duas versões editáveis.
