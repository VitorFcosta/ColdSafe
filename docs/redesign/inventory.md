# P-01 — Inventário de páginas, tarefas e preservação

- **Status:** concluída por análise estática em 27/10/2026.
- **Escopo:** dez rotas atuais, perfis, tarefas, objetos/contextos, navegação,
  estados, base visual e cenários declarados nos testes.
- **Método:** descoberta por codebase-memory-mcp e leitura pontual dos fontes e
  testes. Revisões de operação e administração foram divididas entre dois agentes,
  integradas pelo agente principal com apresentação/conta/Assistente.
- **Não executado:** aplicação, build, testes funcionais, estudo com pessoas,
  medição de contraste ou desempenho. Não há nova evidência renderizada nesta etapa.
- **Limite:** inventário do código atual, com alterações preexistentes preservadas;
  não é auditoria completa de segurança ou comprovação de funcionamento.

Para retomar a P-02, ler as matrizes abaixo, as pendências e somente os fontes
necessários. O [plano](plan.md) conserva as etapas; [referências](references.md)
conserva os princípios externos. Este inventário não aprova novo mapa ou rótulos.

## 1. Páginas e tarefas atuais

As dez rotas vêm de [router/index.ts](../../frontend/src/router/index.ts), linhas
5–67. Apresentação e entrada são públicas; as outras oito exigem sessão na SPA.
As tarefas abaixo descrevem o código, sem atribuir frequência de uso não medida.

| Rota / página | Tarefa principal | Tarefas secundárias existentes | Contexto principal |
| --- | --- | --- | --- |
| `/` — Apresentação | Entender o projeto e acessar demonstração/painel. | Consultar etapas da arquitetura, vídeo legendado e cenários simulados; abrir repositório. | Conteúdo público estático e mídia simulada; sem consulta operacional à API. |
| `/login` — Entrada/cadastro | Criar conta ou entrar. | Alternar modo; corrigir erro; voltar à apresentação; retomar destino interno após login. | Credenciais e sessão; cadastro seguido de login. Não há página de perfil ou recuperação de senha neste inventário. |
| `/dashboard` — Monitoramento | Reconhecer temperatura e atualidade do dispositivo selecionado. | Ver seis grandezas no AIoT, selecionar métrica/período, consultar histórico/tabela, alertas/comparação, previsão e atuadores; comandar LED quando permitido. | Conta → ambiente → registro do dispositivo → MQTT ID → equipamento/telemetria. |
| `/insights` — Insights | Interpretar saúde/RUL, tendência e alertas preditivos do equipamento. | Consultar origem/idade/versão e motivos de indisponibilidade; editar regras quando permitido. | Ambiente/dispositivo selecionados e previsão associada; rascunho de regras próprio. |
| `/digital-twin` — Gêmeo digital | Inspecionar equipamento e componentes por cena ou lista. | Selecionar nove itens por ID, consultar estado/leitura/idade/histórico e previsão associada; controlar LED selecionado quando permitido. | Equipamento, seis sensores, LED, buzzer e seleção local de componente. Requer modo AIoT v3. |
| `/manage` — Ambientes e dispositivos | Consultar e manter o catálogo e limites térmicos. | Criar/renomear ambiente ou dispositivo, desativar dispositivo e editar regras por ambiente; consulta para visualizador. | Ambiente e seus dispositivos/regras; rascunhos de formulários. |
| `/messaging` — Mensageria | Investigar métricas de filas e observação de mensagens. | Consultar taxas/consumidores, amostras privadas e cópias da DLQ, idade/estado do observador. | Infraestrutura agregada e amostras privadas são escopos diferentes; sem seletor de equipamento ao vivo. |
| `/laboratory` — Laboratório | Configurar e acompanhar geração de dataset sintético privado. | Conferir estimativa, retomar job, consultar qualidade/amostra e abrir treinamento com dataset. | Configuração/seed → job → dataset; UUID opcional de ambiente informado livremente. |
| `/training` — Treinamento | Treinar e avaliar saúde/RUL com dataset próprio concluído. | Selecionar/receber dataset, acompanhar job, consultar validação, baseline, métricas, erros, gráficos e pacote. | Dataset → job → resultado/pacote, com partições por equipamento; sem ativação do modelo nesta página. |
| `/assistant` — Assistente | Perguntar sobre dados autorizados da conta e explicações do projeto. | Preparar seis sugestões, acompanhar resposta por partes, cancelar e conferir valores em Insights. | Conta, estado do runtime e conversa local desta página; não é automaticamente o equipamento do cabeçalho. |

## 2. Perfis: página, ação e política da API

O roteador verifica presença de sessão, não papel administrativo. As páginas e
endpoints aplicam restrições adicionais. `viewer` = visualizador, `operator` =
operador, `admin` = administrador. Papel não confirmado mantém escrita bloqueada.

| Área | Consulta na interface atual | Ações e guardas relevantes |
| --- | --- | --- |
| Apresentação/entrada | Visitante; login também pode ser alcançado diretamente. | Formulários de cadastro/login; sessão existente redireciona `/login` para dashboard. |
| Monitoramento/gêmeo | Visualizador, operador e administrador autenticados, no escopo autorizado; gêmeo exige AIoT. | LED para operador/admin. Envio, ACK e observação são distintos; buzzer automático. |
| Insights | Usuários autenticados no escopo autorizado. | PUT de regras preditivas para operador/admin. |
| Gestão | Visualizador consulta; operador/admin também alteram. | GET por usuário; mutações do catálogo/regras por operador/admin, com propriedade. |
| Mensageria | Admin na página e na API. | Somente consulta; métricas agregadas e amostras privadas identificadas. |
| Laboratório/treinamento | A página bloqueia consulta e ação para quem não é admin. | POST de jobs exige admin. GETs de datasets, amostra, job e resultado usam usuário autenticado + dono. Não afirmar que todos esses GETs exigem admin. |
| Assistente | Usuário autenticado; disponibilidade do modelo é uma condição diferente de autorização. | Status/pergunta usam `require_user`; sem ferramentas ou comandos na interface. |

Fontes de autorização: [session.ts](../../frontend/src/features/account/session.ts)
linhas 24–38; [auth.py](../../backend/app/api/auth.py) linhas 353–372;
[aiot.py](../../backend/app/api/aiot.py) linhas 63–112;
[commands.py](../../backend/app/api/commands.py) linhas 57–98;
[catalog.py](../../backend/app/api/catalog.py) linhas 284–355;
[messaging.py](../../backend/app/api/messaging.py) a partir da linha 24;
[jobs.py](../../backend/app/api/jobs.py) linhas 60–158;
[llm.py](../../backend/app/api/llm.py) linhas 43–71.
Os serviços continuam responsáveis por propriedade/escopo. Este quadro não
autoriza alterar política ou substituir autorização por ocultação do menu.

## 3. Objetos e persistência de contexto

| Objeto/contexto | Comportamento identificado | Consequência a considerar na P-02 |
| --- | --- | --- |
| Sessão e papel | Sessão restaurada na aba; identidade consultada; troca/limpeza de sessão limpa seleção salva. Logout com falha não é apresentado como concluído. | Contexto privado e destino devem acompanhar a sessão correta. |
| Ambiente/dispositivo | Registro UUID e MQTT ID são identificadores diferentes. Equipamento, sensores e atuadores têm IDs próprios. | Nome visível não substitui chave de escopo; preservar correspondência entre dado e item. |
| Seleção do dashboard | Ambiente, dispositivo e período são guardados na sessão da aba e revalidados no catálogo. Grandeza não integra essa persistência. | Já existe base de preservação; não presumir armazenamento compartilhado entre todas as vistas. |
| Seleção de Insights/gêmeo | Seleções locais, iniciadas pelo primeiro ambiente/dispositivo ativo autorizado; não usam `dashboardSelection`. Seleção do componente é local e limpa na troca de escopo. | Compartilhar seleção entre vistas é uma mudança futura, com regras de invalidação a definir. |
| Previsão | Evento/entrada, equipamento, versão e idade próprios; zero é válido; disponibilidade e dado atual são distintos. | Contexto de previsão não pode ser renovado só pela chegada de outra informação. |
| Dataset/job | Geração usa `?job=UUID`; dataset concluído liga a `/training?dataset=UUID`; treino também retoma por `?job=UUID`. | Preservar passagem e recarga sem repetir POST; não confundir com seleção de equipamento ao vivo. |
| Mensageria | Métricas globais; amostras privadas dos ambientes ativos do proprietário. Idade da consulta e atualidade do observador são distintas. | Não aplicar um filtro de equipamento só para imitar as telas operacionais. |
| Assistente | Até oito perguntas locais; cada envio independente; sair da página/trocar sessão apaga a conversa. Backend conserva auditoria separada. | Transformar a página em painel persistente mudaria o ciclo de vida; não presumir esse novo comportamento. |

## 4. Caminhos de navegação existentes

- Apresentação: âncoras de funcionamento/demonstração, links ao repositório e
  `/dashboard`; usuário sem sessão passa pelo login e mantém destino em `redirect`.
- Entrada: cadastro e login na mesma rota; sucesso respeita destino interno
  validado ou abre dashboard; marca retorna à apresentação.
- Páginas autenticadas: menus locais repetem os oito destinos autenticados;
  a marca retorna a `/`, não a uma página operacional. O logout trata falha.
- Dashboard oferece ainda `/docs` (documentação da API, fora das dez rotas SPA)
  e, quando diagnóstico habilitado, link RabbitMQ. Isso não constitui página de
  ajuda nem módulo de administração do broker dentro do ColdSafe.
- Estados sem catálogo/dados oferecem caminhos para gestão em páginas operacionais;
  gêmeo liga a Insights para alertas preditivos. Esses links não passam
  explicitamente a seleção de ambiente/dispositivo.
- Geração concluída passa o dataset ao treinamento; treinamento oferece retorno
  ao laboratório. Perguntas do Assistente remetem a Insights para conferência.
- O roteador define título e tenta mover foco para `main h1` nas trocas de rota.
  A presença dessa regra não comprova comportamento acessível em execução.

## 5. Estados e comportamentos a preservar por família

### Apresentação, conta e Assistente

- Apresentação sem API, mídia identificada como simulada, controles/legendas,
  menu móvel, texto alternativo, redução de movimento e limites acadêmicos.
  O conteúdo atual destaca o recorte temperatura/umidade e cadeia legada; não é
  uma descrição completa do AIoT atual. Atualização factual exige revisão própria.
- Entrada/cadastro: validação, erro e envio ocupado; rótulos/autocomplete corretos;
  cadastro seguido de login. Não introduzir seleção de papel no cadastro.
- Assistente: preparação, pronto, pausa, desabilitado, modelo ausente,
  indisponibilidade, acesso negado e espera por limite são estados diferentes.
  Sugestão só preenche; envio é explícito; limite em bytes UTF-8; texto recebido
  não vira HTML; interrupção/cancelamento deixa resposta incompleta, sem reenvio.
  Saúde/RUL sintéticas e possibilidade de erro continuam explícitas.

### Operação, previsão, histórico e gêmeo

- Temperatura normal/atenção/crítica não é diagnóstico global de saúde.
  Carregamento, ausência, leitura vencida e falha são distintos. Idade avança
  localmente mesmo com socket conectado; falha de seção não torna dado antigo atual.
- Grandezas AIoT: temperatura ambiente °C, umidade %, luminosidade %, vibração RMS
  mm/s, corrente A e temperatura do motor °C; ausência não vira zero.
- Dashboard tem quatro períodos e seletor de grandeza. O componente do gráfico
  adapta unidades, resumo e tabela; o contêiner ainda mantém textos fixos em
  temperatura. Essa inconsistência foi identificada, não corrigida na P-01.
- Previsão mantém origem/versão/horários, números vencidos são ocultados; ausência,
  falha e stale não encerram por si só alertas persistentes conhecidos.
  Insights conserva rascunho durante polling e invalida gravação antiga ao trocar escopo.
- Inventário do gêmeo identifica nove itens mesmo sem leitura. Sensores sem
  faixas operacionais não recebem atestado de segurança. Sensores/atuadores
  sem modelo próprio têm saúde/RUL não aplicáveis; previsão é do equipamento.
- Histórico do componente filtra equipamento/ambiente/registro/sensor ID e fixa
  15 minutos. Ventilador/LED/buzzer não têm série própria de estado: o gráfico
  contextual de temperatura precisa continuar identificado como tal.
- Cena/lista compartilham seleção. Stale congela movimento; preferência de movimento
  reduzido e aba oculta suspendem loop; falha WebGL conserva alternativa textual.
  Posições, giro/tremor e escala térmica são ilustrativos. Recursos gráficos são descartados ao sair.
- LED reaproveita controlador/componente do dashboard: envio, pendente, confirmado,
  rejeitado e sem confirmação; impedir reenvio pendente e respeitar papel/conta.

### Gestão, infraestrutura e jobs

- Gestão: catálogo vazio, carregamento, erro, sucesso após API, validação junto aos
  campos, confirmação para desativar e foco de abrir/cancelar inclusão. MQTT ID
  não é editável após cadastro; rascunhos separados. Dispositivos/regras são
  carregados em conjunto com `Promise.all`: não declarar recuperação parcial
  independente desses dois blocos como comportamento já existente.
- Mensageria: último snapshot conservado só com aviso, zero diferente de taxa
  indisponível, consulta/observador com atualidades próprias, acesso revogado limpa
  resultados e resposta antiga não invade nova sessão. Zero consumidores não prova
  writer parado. Não há purga, reentrega DLQ ou controle Docker na interface.
  A interface identifica amostras em memória de até 100 eventos e 100 mensagens
  mortas, limpas ao reiniciar a API; não constituem histórico durável. A amostragem
  não equivale a remover mensagens das filas de negócio ou da DLQ.
- Jobs: fila, execução, conclusão, falha e cancelamento; envio incerto não repete
  POST. Recarga retoma; progresso 100% não substitui estado concluído; polling não
  conserva dados de outra conta/papel/job. `LlmStatus` explica coordenação do runtime.
- Geração: configuração validada/estimativa, dataset privado e amostra sob demanda;
  erro da amostra separado; dados sintéticos fora da telemetria live. UUID opcional
  de ambiente é campo livre, não seletor obrigatório do catálogo.
- Treinamento: reconfirma dataset antes de POST; respeita elegibilidade e mínimos;
  dataset indicado pela URL pode estar fora da lista inicial limitada. Resultado
  confere dataset/modelo/job; erro do resultado conserva job e permite repetir GET.
  Baseline, partições por equipamento, aptidão/rejeição e limites sintéticos
  permanecem explícitos. Treino concluído não significa modelo ativo.

## 6. Fontes mínimas para retomada

Não carregar todos estes arquivos de uma vez: escolher a linha pertinente.

| Área | Fontes de implementação a conferir |
| --- | --- |
| Apresentação | [LandingView.vue](../../frontend/src/views/LandingView.vue), conteúdo/mídia a partir das linhas 24–172. |
| Conta/entrada | [AccessView.vue](../../frontend/src/views/AccessView.vue), linhas 14–52; [session.ts](../../frontend/src/features/account/session.ts), restauração, identidade, seleção e logout. |
| Monitoramento | [FoundationView.vue](../../frontend/src/views/FoundationView.vue), seleção 127–194 e composição 265–449; [use-monitoring-summary.ts](../../frontend/src/features/monitoring/use-monitoring-summary.ts); [TemperatureHistoryChart.vue](../../frontend/src/features/monitoring/TemperatureHistoryChart.vue). |
| Insights | [InsightsView.vue](../../frontend/src/views/InsightsView.vue), seleção 65–96, polling/edição 106–177 e formulário por papel 237–246; [PredictionPanel.vue](../../frontend/src/features/monitoring/PredictionPanel.vue). |
| Gêmeo | [DigitalTwinView.vue](../../frontend/src/views/DigitalTwinView.vue), seleção 48–78 e composição 165–195; [TwinItemPanel.vue](../../frontend/src/features/digital-twin/TwinItemPanel.vue), filtros 27–30 e período na linha 64; [DigitalTwinScene.vue](../../frontend/src/features/digital-twin/DigitalTwinScene.vue); [twin-state.ts](../../frontend/src/features/digital-twin/twin-state.ts). |
| LED compartilhado | [LedControl.vue](../../frontend/src/features/monitoring/LedControl.vue) e [use-actuators.ts](../../frontend/src/features/monitoring/use-actuators.ts). |
| Gestão | [ManageView.vue](../../frontend/src/views/ManageView.vue), seleção 56–97, foco/ações 142–231 e perfis/formulários 265–328. |
| Mensageria | [MessagingView.vue](../../frontend/src/views/MessagingView.vue), atualização/revogação 28–79 e escopos 114–179. |
| Geração | [LaboratoryView.vue](../../frontend/src/views/LaboratoryView.vue), job/requests 54–118, configuração/estados 163–276 e link para treino na linha 217. |
| Treinamento | [TrainingView.vue](../../frontend/src/views/TrainingView.vue), seleção/retomada 48–103, envio 105–125 e resultado 136–151. |
| Assistente | [AssistantView.vue](../../frontend/src/views/AssistantView.vue), estados/sugestões 19–39, sessão/stream 75–160 e limites/links 179–224; [assistant-api.ts](../../frontend/src/features/assistant/assistant-api.ts). |

Base visual já existente: [tokens.css](../../frontend/src/styles/tokens.css)
centraliza cores, Inter, espaços, raios, foco e movimento; [index.css](../../frontend/src/styles/index.css)
carrega a fonte local, números tabulares, foco, link de salto e redução de movimento.
Isso é implementação a aproveitar, sem comprovar conformidade WCAG ou constituir
o design system completo planejado. A cena ainda usa câmera frontal fixa e
geometria simples; a imagem aprovada não é um asset 3D executável.

## 7. Cenários declarados nos testes — não executados

A tabela localiza proteção existente, sem atribuir aprovação ou cobertura atual.
Ler um teste não garante a suficiência da sua asserção; reavaliar na tarefa afetada.

| Área | Arquivos representativos | Cenários identificados |
| --- | --- | --- |
| Apresentação | [landing.spec.ts](../../frontend/e2e/landing.spec.ts) | Independência da API, mídia/legendas, menu móvel/teclado, texto ampliado e redução de movimento. |
| Conta/entrada | [AccessView.spec.ts](../../frontend/src/views/AccessView.spec.ts), [account.spec.ts](../../frontend/src/features/account/account.spec.ts), [catalog-session.spec.ts](../../frontend/src/features/account/catalog-session.spec.ts) | Cadastro/login, erros, logout incerto, identidade desconhecida e 401 antigo versus sessão nova. |
| Monitoramento | [FoundationView.spec.ts](../../frontend/src/views/FoundationView.spec.ts), [dashboard.spec.ts](../../frontend/e2e/dashboard.spec.ts), [dashboard-selection.spec.ts](../../frontend/e2e/dashboard-selection.spec.ts) | Medições, falha parcial, escopo, seleção/período/revalidação, tabela/teclado, comandos e viewer. |
| Insights/previsão | [InsightsView.spec.ts](../../frontend/src/views/InsightsView.spec.ts), [inference.spec.ts](../../frontend/e2e/inference.spec.ts) | Zero válido, versão/expiração, rascunho durante polling, stale e salvamento atrasado. |
| Gêmeo | [DigitalTwinView.spec.ts](../../frontend/src/views/DigitalTwinView.spec.ts), [digital-twin.spec.ts](../../frontend/e2e/digital-twin.spec.ts) | AIoT/legado, IDs, seleção/lista, contexto, WebGL, 320 px, movimento/freshness, descarte e LED. |
| Gestão | [ManageView.spec.ts](../../frontend/src/views/ManageView.spec.ts), [manage.spec.ts](../../frontend/e2e/manage.spec.ts) | Vazios, rascunhos, foco/cancelamento, validação, confirmação e adaptação móvel. |
| Mensageria | [MessagingView.spec.ts](../../frontend/src/views/MessagingView.spec.ts), [test_messaging_api.py](../../backend/tests/api/test_messaging_api.py) | Zero/desconhecido, idade, falha parcial, revogação, isolamento e restrição administrativa. |
| Geração | [LaboratoryView.spec.ts](../../frontend/src/views/LaboratoryView.spec.ts), [test_jobs_api.py](../../backend/tests/api/test_jobs_api.py) | Parâmetros, retomada sem POST, progresso/conclusão, acesso e descarte de resposta antiga. |
| Treinamento | [TrainingView.spec.ts](../../frontend/src/views/TrainingView.spec.ts), [training.spec.ts](../../frontend/e2e/training.spec.ts) | Dataset/URL, envio incerto, elegibilidade, conclusão/aptidão e erro de resultado. |
| Assistente | [AssistantView.spec.ts](../../frontend/src/views/AssistantView.spec.ts), [assistant.spec.ts](../../frontend/e2e/assistant.spec.ts) | Sugestão sem envio, texto seguro, cancelamento/interrupção, limite, revogação e limpeza de sessão. |

Os E2Es simulados mencionados usam fixtures HTTP/WS conforme seus fontes. Arquivos
com sufixo `-real.spec.ts` e harnesses de integração também existem; o nome sozinho
não comprova fronteira real nem execução. Não foram executados nem contabilizados
como aceite nesta P-01. Não há razão para iniciar a pilha pessoal para este inventário.

## 8. Insumos e pendências para P-02

| Achado no código | Questão a resolver, ainda sem escolha de solução |
| --- | --- |
| Oito páginas autenticadas expostas em menus repetidos, com conteúdo de papéis/contextos diferentes. | Como agrupar por tarefa sem esconder destinos úteis ou criar níveis desnecessários? |
| Dashboard guarda seleção; Insights/gêmeo inicializam seleção própria. | Como preservar contexto entre vistas e revalidá-lo após conta/permissão/catálogo mudar? |
| Marca retorna à apresentação; `/docs` só aparece em parte da navegação; não existe rota de ajuda/perfil. | Quais destinos são globais, locais e utilitários, preservando as funções reais? |
| UI de jobs é admin, mas GET privado da API aceita usuário/dono. | Como apresentar acesso com clareza sem ampliar/restringir políticas por suposição? |
| Dados live, dataset/job, conta do Assistente e métricas globais têm escopos distintos. | Que contexto cada cabeçalho mostra, e quais seletores não devem atravessar áreas? |
| Retomada de jobs e passagem de dataset já usam query string. | Como preservar links diretos, recarga e voltar/avançar? |
| Histórico do gêmeo fixa 15 min; imagem oferece quatro períodos. | Qual ampliação será especificada em tarefa futura, mantendo filtro por componente? |
| Gestão carrega dispositivos/regras conjuntamente e landing explica recorte anterior. | Quais lacunas exigem decisão de UX/conteúdo própria, sem fingir solução já implementada? |

Perda de orientação, ambiguidade de rótulos e dificuldade de descoberta são
hipóteses de usabilidade apoiadas nesses achados, não efeitos medidos com pessoas.
O mapa sugerido na conversa permanece proposta; P-01 não renomeia nem move páginas.

## 9. Resultado, verificação e checkpoint

- Criado este inventário para registrar as dez rotas, tarefas, perfis, objetos,
  estados, caminhos, base visual e cenários existentes com fontes locais.
- Atualizados somente o [guia](README.md) e o [plano](plan.md) para localizar a
  entrega e marcar P-01 concluída no escopo estático.
- Dependências adicionadas: **nenhuma**. Interface, testes, contratos, permissões,
  configurações e histórico AIoT permaneceram inalterados nesta etapa.
- Verificações documentais: links locais, correspondência das dez rotas com o
  roteador, referências de arquivos e formatação do diff. São verificações do
  documento, não execução de teste de produto.
- Revisões independentes de operação e administração conferiram seus escopos;
  incorporada a ressalva sobre amostras efêmeras da Mensageria.
- Limites: sem renderização nova, teste com usuários, verificação de execução,
  cobertura atual, calibração física ou medição de desempenho.

**Próxima etapa proposta: P-02 — Arquitetura da informação**, a iniciar após escolha
do usuário. Usar este inventário e o plano, consultar apenas os fontes necessários
e produzir mapa/fluxos; não implementar nem considerar o mapa aprovado por este registro.
