# P-06 — Roadmap de implementação do redesign

**03/11/2026 · RD-01 a RD-17 concluídas; RD-18 concluída por aceite do usuário, com ressalvas técnicas. Ocultação de dados automáticos implementada; ensaio VoiceOver dispensado pelo usuário, sem validação presumida.**
Elaboração documental P-06 concluída em 28/10/2026.
O usuário aprovou a P-05 e escolheu a P-06. A implementação começou pela RD-01 em 29/10/2026, após escolha do usuário.
A referência é o [design system aprovado](../design-system/README.md) aplicado nas
[composições aprovadas](../compositions/README.md), com contratos do inventário/mapa.
IDs RD são tarefas de execução; P são etapas de planejamento; F/C/G/M/S são referências
visuais e de comportamento. Não misturar esses IDs com os cartões históricos B2.

## Decisões confirmadas e sequência

O gêmeo será **3D real no navegador**, selecionável e conectado aos dados autorizados.
A imagem é referência de acabamento. Câmera fixa em três quartos não elimina volume
3D; controles de órbita/zoom não fazem parte desta versão. Movimento ilustrativo não
é RPM medido nem simulação física validada. Falha WebGL preserva lista e inspeção.

Ordem sugerida: RD-01 → RD-02 → RD-03 → RD-04 → RD-05 → RD-06, depois migrações
por família conforme dependências abaixo. O experimento vem cedo para reduzir a
incerteza do acabamento/desempenho; não depende das migrações. RD-09 requer também
a decisão do experimento aceita. **RD-02 encerrada em 30/10 por confirmação do usuário de que os testes
pendentes passaram; medições históricas preservadas. RD-09 concluída em 31/10 com testes, medição desktop e ciclo de vida verificados.** Não há calendário ou estimativa de duração prometida.

| Fase | Tarefa | Dependências RD | Status |
| --- | --- | --- | --- |
| Base | [RD-01 — Fundamentos visuais e primeiros usos](RD-01.md) | — | Concluída em 29/10/2026 |
| Viabilidade cedo | [RD-02 — Experimento do 3D real](RD-02.md) | — | Concluída em 30/10/2026 — testes confirmados pelo usuário |
| Navegação | [RD-03 — Estrutura compartilhada e acesso](RD-03.md) | 01 | Concluída em 29/10/2026 |
| Comportamentos | [RD-04 — Contexto de Monitoramento](RD-04.md) | 03 | Concluída em 29/10/2026 |
| Comportamentos | [RD-05 — Edição e transições](RD-05.md) | 04 | Concluída em 30/10/2026 |
| Comportamentos | [RD-06 — Retomada de jobs](RD-06.md) | 03 | Concluída em 30/10/2026 |
| Monitoramento | [RD-07 — Visão geral](RD-07.md) | 04 | Concluída em 30/10/2026 |
| Monitoramento | [RD-08 — Saúde e previsões](RD-08.md) | 05, 07 | Concluída em 30/10/2026 |
| Gêmeo real | [RD-09 — Cena de produção](RD-09.md) | 02, 01 | Concluída em 31/10/2026 |
| Gêmeo real | [RD-10 — Página e inspeção](RD-10.md) | 04, 07, 09 | Concluída em 31/10/2026 |
| Gestão | [RD-11 — Ambientes e dispositivos](RD-11.md) | 05 | Concluída em 31/10/2026 |
| Dados e modelos | [RD-12 — Dados sintéticos](RD-12.md) | 05, 06 | Concluída em 31/10/2026 |
| Dados e modelos | [RD-13 — Treinamento e diagnósticos](RD-13.md) | 12 | Concluída em 31/10/2026 |
| Infraestrutura | [RD-14 — Filas e mensagens](RD-14.md) | 03 | Concluída em 31/10/2026 |
| Utilitário | [RD-15 — Assistente](RD-15.md) | 03 | Concluída em 31/10/2026 |
| Acesso | [RD-16 — Entrada/cadastro](RD-16.md) | 03 | Concluída em 31/10/2026 |
| Pública | [RD-17 — Apresentação](RD-17.md) | 01 | Concluída em 02/11/2026 |
| Fechamento | [RD-18 — Verificação integrada/documentação](RD-18.md) | 08, 10, 11, 13, 14, 15, 16, 17 | Concluída por aceite do usuário, com ressalvas, em 02/11/2026 |

A dependência exige aceite atendido ou limitação formalmente resolvida; não basta
ter editado o arquivo. Os números indicam organização, não obrigação de bloquear
frentes independentes. Compartilhar arquivos exige sequência ou responsabilidade
explícita: RD-03 toca navegação nas oito views; RD-04/05/06 alteram comportamentos
que suas migrações devem preservar. Evitar agentes editando a mesma view em paralelo.
RD-07 refina componentes de domínio consumidos também por RD-08/RD-10.

## Uma tarefa por retomada

1. Ler este índice e o cartão escolhido; abrir somente IDs/seções nele indicados.
   A [matriz de fontes/testes da P-01](../inventory.md#6-fontes-mínimas-para-retomada)
   ajuda a localizar código. Não carregar todos os cartões, PDFs e histórico B2.
2. Conferir dependências e árvore de trabalho. Preferir grafo MCP para descoberta;
   código/contratos atuais precisam confirmar a evidência datada do planejamento.
3. Explicar escopo antes de editar. Preservar alterações existentes; usar testes
   antes de lógica nova relevante, com integração real nos primeiros consumidores.
4. Fazer verificação proporcional e revisão do resultado. Explicar arquivos
   criados/alterados, motivo, funcionamento e dependências adicionadas (ou nenhuma).
5. Preencher checkpoint do cartão: resultado, testes executados, evidências/data,
   versão Git/alterações locais, limites e próxima ação. Atualizar status neste
   índice apenas quando mudar. Salvar antes de compactar; não iniciar próxima tarefa.

O fluxo atual serve de base, não autoriza inventar novos endpoints, permissões ou
bibliotecas. Os caminhos dos cartões são pontos de partida, não promessa de que a
arquitetura continuará idêntica. Se surgir conflito material de produto, registrar
alternativas e resolver o conflito antes de ampliar o escopo.

## Critérios comuns de execução e verificação

- Cada entrega conserva dez rotas, papéis, isolamento de conta e funções existentes.
  Casos novo/ocupado/vazio/erro/restrito/desatualizado são aplicados conforme o domínio.
- Reutilizar Vue/TypeScript, estilos, Chart.js, Three.js e componentes existentes.
  Biblioteca só com necessidade comprovada; nenhuma instalação foi escolhida aqui.
- Para nova lógica de contexto, rascunho, retomada e pausa: teste significativo
  antes da implementação, integração e E2E pertinente. Mudança puramente visual
  não exige teste que apenas repita CSS. Testes existentes não são descartados
  para acomodar regressões; seletores podem ser atualizados preservando intenção.
- Conferir scripts/versão do Node em [package.json](../../../frontend/package.json).
  Na criação do plano existem `npm run typecheck`, `npm run build`,
  `npm run test:unit:run -- <arquivo>`, `npm run test:coverage` e
  `npm run test:e2e -- <spec>`. São exemplos para executar dentro de `frontend/`,
  depois de conferir configuração, e não resultados já obtidos.
- Testes de uma tarefa começam pelo escopo afetado; build/tipagem quando código
  muda. Meta de cobertura do projeto: pelo menos 80%, com escopo e métricas
  registrados, sem manipular exclusões. RD-18 consolida verificação integrada;
  não adia a qualidade das entregas anteriores para o fim.
- Revisão visual em rodada conjunta desktop/celular, correção dos problemas
  encontrados e confirmação delimitada. Conferir 320 px, texto ampliado, teclado,
  foco, nomes acessíveis, contraste e movimento reduzido. PDF não é teste de reflow.
- Fontes e valores da P-04 orientam; contraste se verifica nas cores adjacentes
  realmente renderizadas. Avaliar atualizações automáticas além da animação 3D.
  Registrar uso de leitor de tela, navegador/dispositivo e limitações.
- E2E com respostas controladas comprova fluxo da UI, não serviço real. Separar
  testes reais/pesados pela configuração; não iniciar containers, gerar milhões de
  linhas, treinar modelos ou atuar em dispositivo pessoal por reflexo. Se a mudança
  exigir integração real, delimitar ambiente e ação antes da execução.
- RD-02/RD-09 precisam de WebGL/GPU e hardware identificados para alegar desempenho.
  Se não houver dispositivo móvel real, declarar a lacuna. Nenhuma foto ou medição
  antiga comprova a cena nova. Recursos/medidas seguem a [estratégia](../compositions/3d-strategy.md).
- Teste de descoberta com pessoas permanece previsto no protocolo P-03; não contar
  agentes ou aprovação do proprietário como participantes independentes. Sem
  pessoas disponíveis, registrar a lacuna e não declarar usabilidade comprovada.

## Cobertura dos contratos transversais

| Contrato/fluxo | Responsável principal | Integração/verificação |
| --- | --- | --- |
| Dez rotas, identidade pendente, perfis e destino de login | RD-03 | RD-16, RD-18 |
| Environment/device, URL, aba, histórico e respostas antigas | RD-04 | RD-07, RD-08, RD-10, RD-18 |
| Rascunho antes de mudar rota/escopo; sessão prevalece | RD-05 | RD-08, RD-11, RD-12, RD-13 |
| Jobs conhecidos, relação job/dataset e zero POST de retomada | RD-06 | RD-12, RD-13, RD-18 |
| Frescor, ausência/zero, histórico, previsão e ACK/observação | RD-07 | RD-08, RD-10 |
| 3D real, movimento ilustrativo, pausa, IDs e fallback | RD-02, RD-09 | RD-10, RD-18 |
| Gestão com contexto próprio e confirmação de desativação | RD-11 | RD-18 |
| Métricas globais versus amostras privadas/efêmeras | RD-14 | RD-18 |
| Conversa local, saída, stream incompleto e texto seguro | RD-15 | RD-18 |
| Conteúdo acadêmico, mídia real e ilustração identificada | RD-17 | RD-18 |

## Checkpoint da elaboração P-06

Criados este índice e 18 cartões locais para retomada, com dependências, leitura
mínima, responsabilidade, aceite e validação. Nenhum cartão iniciado, código do
aplicativo alterado ou dependência adicionada. Aprovação P-05 registrada em seus
documentos; suas imagens e evidências históricas foram preservadas.

Verificação documental em 28/10/2026: 435 links/âncoras locais em 32 documentos,
18 cartões com status/dependências coerentes com o índice, grafo sem ciclos e
cobertura M-01 a M-10. Formatação conferida também nos arquivos novos;
`git diff --check` sem erro. Hashes de 627 arquivos rastreados fora do redesign
confirmaram preservação das alterações preexistentes durante esta tarefa.

Revisão independente de planejamento incorporada: RD-09 entrega o controle mínimo
acessível de pausa junto da cena, sem adiar essa capacidade para RD-10, que refina
sua composição. Demais contratos transversais e estados de aprovação conferidos.
Sem app, build, teste funcional, benchmark ou pesquisa com participantes nesta P-06.

**Próxima ação (02/11/2026):** aguardar escolha do usuário. A sequência foi
encerrada por seu aceite; o [checkpoint RD-18](RD-18.md#checkpoint) preserva as
ressalvas de pausa/frequência dos dados e leitor de tela atual. Essas pendências
não foram corrigidas nem validadas pelo encerramento documental.
O checkpoint da elaboração P-06 acima é evidência histórica documental, não
resultado da implementação.
