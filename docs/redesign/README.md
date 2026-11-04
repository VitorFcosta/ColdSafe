# ColdSafe — redesign da interface

**Atualizado em 03/11/2026. RD-01 a RD-17 concluídas; RD-18 concluída por aceite do usuário, com ressalvas técnicas. Controle dos dados automáticos implementado nesta retomada.**

Este guia separa a implementação atual do planejamento P-01 a P-06 preservado
abaixo. O [roadmap](tasks/README.md) organiza as entregas e o
[checkpoint RD-18](tasks/RD-18.md#checkpoint) registra o estado da verificação
integrada, testes executados, limites e próxima ação. Concluir as migrações de
página não encerra automaticamente a verificação integrada.

## Retomar

1. Ler este guia, o [índice de tarefas](tasks/README.md) e somente o cartão
   escolhido; para a rodada atual, [RD-18](tasks/RD-18.md).
2. Consultar somente os IDs/referências necessários e conferir o código atual.
3. Separar decisão aprovada, proposta, evidência de código e teste executado.
4. Encerrar a etapa com resultado, limites e próxima ação; não iniciar outra
   tarefa automaticamente.

| Preciso de… | Ler |
| --- | --- |
| Conferir implementação, status e evidências por tarefa | [Roadmap e cartões RD](tasks/README.md) |
| Retomar a verificação integrada e suas pendências | [RD-18 — Checkpoint](tasks/RD-18.md#checkpoint) |
| Entender a sequência histórica do planejamento | [Plano P-01 a P-06](plan.md) |
| Retomar o inventário das páginas, perfis e comportamentos | [P-01 — Inventário estático](inventory.md) |
| Examinar o mapa proposto e regras de navegação/contexto | [P-02 — Arquitetura da informação](information-architecture.md) |
| Conferir confirmação do mapa, revisão dos caminhos e testes ainda pendentes | [P-03 — Avaliação dos caminhos](path-evaluation.md) |
| Consultar regras visuais, componentes e gêmeo de referência | [P-04 — Design system](design-system/README.md), [tokens implementados](../../frontend/src/styles/tokens.css) |
| Consultar composições de referência das dez páginas e estratégia 3D | [P-05 — Composições](compositions/README.md) |
| Conferir fontes, aplicação e limites | [Referências](references.md) |
| Consultar a direção visual aprovada | [Imagem conceitual do gêmeo](assets/gemeo-digital-conceito.png) |
| Conferir funções e restrições do produto | [Produto frontend](../../frontend/PRODUCT.md), código atual e contratos pertinentes |
| Consultar o redesign anterior | [Relatório histórico](../testing/redesign-portfolio.md), somente quando necessário |

## Estado atual e limites da verificação

RD-01 a RD-17 implementaram fundamentos, estrutura e comportamentos
compartilhados, migrações das páginas, cena/inspeção 3D e apresentação pública.
Cada cartão conserva seu resultado e sua evidência datada. As pranchas P-04/P-05
são referências aprovadas de planejamento, não capturas ou resultados de teste.
Dados, permissões e contratos precisam corresponder ao código atual.

RD-18 foi encerrada por aceite explícito do usuário (“pode colocar como feito”),
com ressalvas técnicas preservadas. Em 03/11, o usuário pediu o fechamento e a
pendência de atualização automática foi resolvida em `FoundationView`,
`InsightsView`, `DigitalTwinView` e `MessagingView`: “Ocultar dados ao vivo”
remove valores, gráficos, relógios e estados automáticos da apresentação visual
e acessível, mantendo coleta, autorização e acompanhamento de comandos. Mostrar
revela os dados mais recentes recebidos. A cena é suspensa enquanto oculta,
conservando seleção e pausa manual. O ensaio com VoiceOver foi dispensado pelo
usuário, sem presumir validação assistiva. Consulte os resultados no checkpoint.

O protocolo P-03 com participantes não foi executado. A rodada integrada de
leitor de tela deve ser consultada no checkpoint RD-18; não há resultado final
presumido aqui. Existe um [ensaio básico histórico de VoiceOver na RD-10](tasks/RD-10.md),
com alcance e limites próprios, que não substitui essa verificação. Aprovação do
proprietário e testes automatizados não comprovam descoberta por participantes
independentes nem conformidade WCAG integral.

Não foi criado `DESIGN.md`: o [design system existente](design-system/README.md),
as [composições](compositions/README.md), os tokens e os cartões já oferecem as
referências necessárias. Duplicar essa fonte normativa exigiria sincronização
sem acrescentar informação. Essa decisão documental não é nova aprovação estética.

## Histórico P-01 a P-06

As seções seguintes registram o estado no fechamento de cada etapa de
planejamento. Expressões como “futuro” ou “não iniciado” têm esse contexto;
o estado da implementação deve ser consultado nos cartões RD.

### O que foi confirmado durante o planejamento

- Escopo: toda a interface, organizada em fases, com atenção especial ao gêmeo.
- Direção: Precisão operacional; aplicação clara, Inter e acento petróleo.
- A imagem conceitual do gêmeo foi aprovada como referência de aparência e
  organização, sem confirmar hardware, posições físicas ou valores simulados.
- O planejamento deve incluir arquitetura da informação, heurísticas,
  acessibilidade e design system antes do roadmap detalhado de implementação.
- As tarefas futuras devem ser pequenas e retomáveis, como os cartões AIoT.
- Na P-03, o usuário confirmou os quatro agrupamentos, os utilitários e os nomes
  Saúde e previsões e Filas e mensagens; ver [registro](path-evaluation.md#2-confirmação-do-usuário).
- Em 28/10/2026, o usuário aprovou a P-04 e escolheu a P-05: “próxima, essa ficou boa”.
- Em 28/10/2026, o usuário aprovou a P-05, confirmou 3D real e escolheu a P-06.
- No fechamento da P-06, a etapa produziu o roadmap e nenhuma tarefa de
  implementação havia sido escolhida. RD-01 iniciou posteriormente, em 29/10/2026.

### Propostas no fechamento do planejamento

O mapa Monitoramento / Ambientes e dispositivos / Dados e modelos / Filas e
mensagens foi confirmado para o planejamento. Os mecanismos de contexto,
retomada de jobs e avisos documentados na [P-02](information-architecture.md)
eram especificações futuras naquele fechamento; sua execução está registrada
nos cartões RD. Confirmação dirigida não comprova descoberta
por outras pessoas nem funcionamento da interface.

As dez rotas atuais permanecem a referência de inventário; nenhuma nova página,
mudança de URL, funcionalidade ou permissão está aprovada por este documento.
A apresentação pública e entrada/cadastro fazem parte do escopo, com necessidades
de navegação diferentes das páginas autenticadas.

### Consolidação inicial

Consolidado o processo de planejamento, sua base de referências e a imagem
aprovada. Nenhuma interface, contrato, configuração ou dependência foi alterada.
O histórico B2 permanece separado e não foi replanejado.

Verificações desta entrega: integridade da cópia da imagem, links locais e
formatação do diff. Esses checks documentais não representam teste do aplicativo.

Não foram executados testes funcionais, estudos com usuários ou medições de
desempenho nesta entrega. A imagem gerada não demonstra viabilidade do modelo 3D
no navegador nem conformidade de acessibilidade.

### P-01 — Inventário concluído em 27/10/2026

O [inventário](inventory.md) mapeia as dez páginas, tarefas, perfis, contextos,
estados, navegação existente, base visual e cenários declarados nos testes.
Conclusão por leitura de código/testes e conferência documental; sem executar
aplicação, build, testes funcionais ou estudo com pessoas.

### P-02 — Proposta documentada em 27/10/2026

A [arquitetura proposta](information-architecture.md) preserva as dez rotas e
especifica destinos, nomes candidatos, contexto, perfis, celular e fluxos.
P-02 concluída como elaboração documental; não houve aprovação do mapa,
implementação, teste com pessoas ou validação funcional.

### P-03 — Avaliação documental concluída em 27/10/2026

O [relatório](path-evaluation.md) registra 11 cenários, as dez heurísticas,
confirmação dirigida do usuário e ajustes de retomada, acesso, links e rascunhos.
Inclui protocolo de teste da árvore ainda não aplicado. Não houve estudo com
participantes, teste funcional ou validação visual/de acessibilidade.

Próxima ação registrada no fechamento da P-03: P-04, posteriormente escolhida
pelo usuário. A P-06 posteriormente definiu 18 cartões RD;
a lista anterior de 20 cartões era rascunho.

### P-04 — Especificação entregue para revisão em 27/10/2026

O [design system proposto](design-system/README.md) reúne fundamentos,
componentes/padrões e linguagem do gêmeo, com duas pranchas estáticas e PDF.
Identifica valores existentes, mudanças propostas e contratos a preservar.
Os exemplos não são uma biblioteca de componentes ou interface implementada.

No fechamento de 27/10, a aprovação estava pendente. Em 28/10/2026, o usuário
aprovou a especificação para planejamento e escolheu avançar à P-05.

### P-05 — Composições entregues para revisão em 28/10/2026

O [caderno de composições](compositions/README.md) aplica o sistema às dez rotas,
com desktop/celular, estados comuns, especificação do conteúdo fora do enquadramento
e estratégia do gêmeo. Onze pranchas SVG/PNG e PDF; imagem ilustrativa com origem
e prompt documentados. Conferências e limites registrados no guia da etapa.

Após esclarecer 3D real versus imagem, o usuário aprovou P-05 e escolheu P-06.
Os artefatos continuam exemplos estáticos; aprovação não substitui teste funcional.

### P-06 — Roadmap documentado em 28/10/2026

O [roadmap](tasks/README.md) organiza 18 cartões de execução: fundamentos,
experimento 3D cedo, navegação/comportamentos, migração das páginas, cena/inspeção
3D e verificação integrada. Cada cartão inclui leitura mínima, dependências,
responsabilidade, aceite, validação e checkpoint a preencher.

**Próxima ação registrada naquele fechamento:** escolher uma tarefa de
implementação, com sugestão de RD-01. Todos os cartões estavam não iniciados;
nenhuma implementação foi feita pela elaboração documental da P-06.
Para a próxima ação atual, consultar o [checkpoint RD-18](tasks/RD-18.md#checkpoint).
