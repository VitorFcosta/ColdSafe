# Componentes e padrões — P-04

**v0.1 de 27/10/2026, aprovada para planejamento em 28/10/2026.** IDs C identificam fichas de design. Não são nomes
de componentes Vue criados nem uma API de biblioteca. Valores visuais seguem os
[fundamentos](foundations.md); acesso/contexto seguem a [P-02](../information-architecture.md).

## C-00 — Base existente

| Padrão | Evidência local | Decisão de planejamento |
| --- | --- | --- |
| Botões/campos/cadastro | [AccessView](../../../frontend/src/views/AccessView.vue), [ManageView](../../../frontend/src/views/ManageView.vue) | Consolidar estilos/estados locais após comparar usos; não presumir componente genérico pronto. |
| Navegação | [FoundationView](../../../frontend/src/views/FoundationView.vue), demais views | Novo padrão compartilhado deverá substituir repetição, usando o mapa confirmado. |
| Medição/previsão | [PredictionPanel](../../../frontend/src/features/monitoring/PredictionPanel.vue), [InsightsView](../../../frontend/src/views/InsightsView.vue) | Preservar contrato de domínio; organizar valor, origem e estado. |
| Histórico | [TemperatureHistoryChart](../../../frontend/src/features/monitoring/TemperatureHistoryChart.vue) | Reaproveitar suporte às grandezas, lacunas, resumo, tabela e fuso. |
| LED | [LedControl](../../../frontend/src/features/monitoring/LedControl.vue), [use-actuators](../../../frontend/src/features/monitoring/use-actuators.ts) | Reutilização real entre dashboard e gêmeo; não duplicar lógica. |
| Estado do LLM | [LlmStatus](../../../frontend/src/features/llm/LlmStatus.vue) | Preservar comportamento específico; aviso genérico não deve absorver seu polling. |
| Jobs/resultados | [LaboratoryView](../../../frontend/src/views/LaboratoryView.vue), [TrainingView](../../../frontend/src/views/TrainingView.vue), [TrainingTarget](../../../frontend/src/features/training/TrainingTarget.vue) | Padronizar apresentação; conservar estados, resultados e isolamento por dono. |
| Inspeção | [TwinItemPanel](../../../frontend/src/features/digital-twin/TwinItemPanel.vue) | Preservar identidade e dados; detalhado em G-01 a G-05. |

## C-01 — Ações e links

- **Primária:** accent/accent-ink, raio 8, F-04. Um destaque principal por grupo
  de tarefa, não necessariamente um por página inteira. Texto com verbo e objeto.
- **Secundária:** surface, ink e control-border; cancelar/voltar/consultar quando
  concorrentes com uma ação principal. Ação discreta usa link se mudar de destino.
- **Perigosa:** texto e/ou preenchimento critical conforme hierarquia; nomear
  consequência, por exemplo “Desativar dispositivo”. Não colorir navegação comum de vermelho.
- **Estados:** repouso, hover, foco, pressionado, indisponível e ocupado. Ocupado
  conserva largura/contexto, apresenta verbo (“Salvando…”) e bloqueia duplicação.
  Indisponibilidade tem motivo próximo; não depender de tooltip em controle desabilitado.
- **Acesso:** ação não permitida não deve parecer executável. Consulta pode mostrar
  explicação de papel sem inventar fluxo de solicitação de acesso.

Botão executa ação; link navega. Ícone decorativo não repete o nome para leitor de
tela. Ícone sozinho só em controle inequívoco, com nome acessível e alvo F-04.
Mensagens de erro/sucesso ficam junto da ação ou seção; não dependem de toast passageiro.

## C-02 — Campos, seletores e edição

Label persistente acima; ajuda abaixo; erro específico próximo, associado ao campo.
Campo: surface, ink, borda control-border de 1 px, raio 8, corpo 16/24 e altura
mínima 44 px. Erro usa borda/texto critical mais mensagem, sem remover foco.
Placeholder é exemplo opcional, nunca substitui label. Unidade aparece fora do valor digitado.

Estados: vazio, preenchido, foco, inválido, somente leitura, desabilitado e carregando
opções. Somente leitura mantém conteúdo selecionável quando adequado. Preservar
autocomplete de acesso e select nativo para listas simples. Sem busca/combobox
customizado até haver necessidade comprovada. Senha não é reexibida por padrão.

Agrupar campos por objeto; instruções antes do grupo; cancelar e salvar ao final.
Falha conserva rascunho autorizado; polling não sobrescreve edição. Mudança de
escopo resolve a decisão da P-03 antes de limpar. Validação textual identifica
campo e correção; no envio inválido, orientar foco ao erro sem anúncios repetitivos.

## C-03 — Navegação e contexto

Aplicar quatro áreas da P-02 conforme papel, com utilitários separados. Links
locais estilizados como abas continuam links de rota, não `tablist` com painéis
ocultos. Link atual usa peso, marcador/linha e `aria-current`; ícone é complementar.
Cabeçalho contém título, propósito quando útil e apenas contexto da família.

Menu móvel proposto como painel modal: botão “Menu”, estado expandido, título,
fechar/Escape, foco contido e retorno ao acionador; navegação concluída fecha painel
e orienta foco ao título da página. Essa decisão exige verificação no navegador.
Menus de links não ganham papel ARIA `menu` por aparência.
[Referência W3C](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/).

Ambiente/dispositivo identificados nas três vistas operacionais, com largura
adaptável. Jobs, infraestrutura e Assistente conservam seus escopos próprios.
Não acrescentar seletor que sugira filtro não aplicado. API/documentação externa
informa abertura em nova aba. A marca interna segue o destino aprovado na P-02.

## C-04 — Estados, avisos e confirmação

| Situação | Apresentação proposta | Cuidado de comportamento |
| --- | --- | --- |
| Carregando | Estrutura estável e texto curto; placeholder só onde haverá dado | `aria-busy`/status pertinente; não anunciar cada polling. |
| Vazio | Objeto ausente + explicação + ação disponível ao papel | Sem zero fictício ou convite a cadastro para viewer. |
| Dado antigo | Cor stale, idade e “Última leitura conhecida” | Não dizer que conexão aberta confirma atualidade. |
| Erro de seção | Mensagem inline e “Tentar consultar novamente”, quando permitido | Preservar demais seções válidas; não prometer recuperação independente onde a carga é conjunta. |
| Sucesso | Confirmação junto da ação | Não deduzir confirmação de comando por envio HTTP. |
| Restrição/identidade pendente | Explicação e recuperação adequada à P-03 | Papel desconhecido não é viewer confirmado. |
| Alerta do equipamento | Ícone/forma + nome da condição + origem/horário | Separar condição física estimada de erro do serviço. |

Aviso informativo usa status discreto; alerta assertivo só para erro/urgência que
exige atenção imediata. Não ler valores a cada atualização. Diálogo só quando a
decisão interrompe a tarefa de fato: descarte ou desativação. Mostrar objeto e
consequência. Diálogos e menu modal têm nome acessível, fundo temporariamente
indisponível à interação/leitura assistiva e foco contido; foco inicial no título
ou ação segura conforme conteúdo, Escape/cancelamento e retorno ao acionador.
No menu após navegação, foco segue para o título da nova página. Revogação/expiração
não aguardam confirmação de rascunho.

## C-05 — Medições, previsão e tabela

Medição: nome → valor/unidade → condição pertinente → idade/origem. Em seis
grandezas, usar faixa/grid coerente, sem tornar todas grandes cartões de destaque.
“Na faixa” só quando existe faixa; sensores sem regra usam “Leitura atual” como
texto proposto de atualidade, sem alterar o estado recebido nem inventar diagnóstico.

Previsão: “Saúde estimada” e “Vida útil restante estimada”, unidade, equipamento,
origem sintética, idade da entrada e versão. Zero é válido; indisponível não é zero.
Conservar estados de modelo ausente, warm-up, features inválidas, erro e leitura
vencida; não exibir como atual um valor que o contrato manda ocultar.

Tabela: caption/título, cabeçalhos associados, texto à esquerda, números/unidades
coerentes e alinhados à direita. Linhas têm separadores suaves; alternância de fundo
só quando ajuda o rastreamento. IDs quebram ou permitem acesso ao valor completo.
Em celular, rolagem fica numa região identificada e acessível por teclado; não
converter automaticamente toda tabela em cards nem ocultar colunas essenciais.

## C-06 — Gráficos

Título responde qual grandeza/objeto/período; unidade e fuso explícitos. Observado
usa accent em superfície clara; referência/baseline usa ink-muted e traço/forma
distinta. Rótulo/legenda não depende só da cor. Evitar sobrepor unidades diferentes.
Gráfico de barras começa em zero; linha pode ter faixa pertinente com eixo claro,
sem sugerir magnitude falsa. Usar valores válidos do contrato, sem suavização que
invente picos ou continuidade nas lacunas.

Limites térmicos atuais ficam nomeados como **atuais**, sem alegar que vigoravam no
passado. Linha/contorno identificável acompanha faixa colorida. Séries adicionais
exigem diferenciação verificada antes de ampliar a paleta; os casos iniciais usam
os dois papéis acima. Resumo textual e tabela oferecem a informação fora do canvas.

Vazio, carga, erro e cobertura parcial aparecem junto do gráfico. Tooltip não é
única fonte de leitura. Medições/gráficos operacionais não animam contadores.
Dashboard conserva quatro períodos; gêmeo conserva 15 min até mudança específica.

## C-07 — Comando e processo

**LED:** apresentar estado observado com idade e estado do pedido em regiões
distintas do mesmo controle. Enviando, aguardando confirmação, confirmado, rejeitado
e sem confirmação possuem textos próprios. Enquanto envia/aguarda, bloquear
duplicação conforme controlador atual; retorno à vista apenas consulta. Sem
confirmação não oferece reenvio automático. Não mudar buzzer/motor em controle manual.

**Job:** etapa, estado, ID e progresso quando conhecido. Percentual desconhecido
é indeterminado; 100% não substitui conclusão. Treino concluído não significa apto
ou ativo. Resultado indisponível permite consulta novamente, sem reexecutar treino.
Envio incerto explica possibilidade de criação e não duplica POST.
Retomar geração/treinamento são ações propostas da P-03 para jobs conhecidos.

## C-08 — Famílias de página e conteúdo

| Família / rotas atuais | Padrão de composição a detalhar na P-05 |
| --- | --- |
| Pública `/` | Narrativa acadêmica, mídia identificada/legendada, tema escuro, CTA de demonstração/acesso; preserva conteúdo e limites. |
| Acesso `/login` | Formulário claro e compacto, modos existentes, foco em preenchimento/erros e retorno ao destino solicitado. |
| Operação `/dashboard`, `/insights` | Contexto e atualidade → leitura/estimativa → investigação → ações/regras pertinentes. |
| Inspeção `/digital-twin` | Mesmo contexto → cena/lista → detalhe/histórico; regras G. |
| Cadastro `/manage` | Lista de objetos → seleção/edição → revisão de ação; evitar formulário longo sem agrupamento. |
| Dados `/laboratory`, `/training` | Configuração → execução → resultado, com retomada e limites do experimento. |
| Infraestrutura `/messaging` | Escopo/atualidade → métricas → amostras; agregação global e dados privados identificados. |
| Assistente `/assistant` | Estado/escopo → pergunta → resposta progressiva → conferência; conversa local e limites visíveis. |

Para Assistente, sugestões preenchem sem enviar; cancelamento deixa resposta
incompleta. Não inserir texto recebido como HTML ou tratá-lo como comando. Na
resposta progressiva, manter foco no controle usado e anunciar início, conclusão,
cancelamento e erro, sem reler a resposta inteira a cada fragmento; o texto recebido
continua navegável. Na apresentação, mídia sem autoplay e com controles/legendas
existentes; dados de
exemplo identificados. Descrições de páginas não criam funções ou rotas novas.

## C-09 — Critério de revisão futura

Em cada migração, verificar: estado comum e exceções pertinentes; teclado/foco;
nomes longos/320 px; papel e conta; dados reais versus exemplo; consulta sem
duplicar ação; contraste dos estados aplicados. Reusar testes de domínio e criar
teste focado para comportamento novo. Esses testes não foram executados na P-04.
