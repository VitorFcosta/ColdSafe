# Plano do redesign ColdSafe

**Versão de planejamento: 28/10/2026.** Este arquivo define o processo de trabalho,
não descreve uma interface implementada. Escopo e direção visual foram confirmados;
o mapa de navegação foi confirmado na P-03 por revisão dirigida. A especificação
do design system e as composições foram aprovadas para planejamento. Roadmap
com 18 cartões documentado; todas as tarefas de implementação estão não iniciadas.

## Objetivo e público

Ajudar o operador a reconhecer equipamento, estado, atualidade e necessidade de
atenção; ajudar o administrador a encontrar cadastro, dados/modelos e infraestrutura;
explicar o protótipo ao visitante e avaliador acadêmico.

As páginas operacionais priorizam completar tarefas (modo Operate). A apresentação
pública explica o projeto e encaminha à demonstração/acesso (modo Persuade).
Uma composição do gêmeo não especifica a apresentação ou os formulários.

## Sequência e entregas

**P-01 concluída por análise estática em 27/10/2026:** [inventário](inventory.md).
**P-02 concluída como proposta documentada em 27/10/2026:** [arquitetura](information-architecture.md).
**P-03 concluída por revisão documental e confirmação dirigida em 27/10/2026:**
[avaliação dos caminhos](path-evaluation.md).
**P-04 especificada em 27/10 e aprovada para planejamento em 28/10/2026:**
[design system](design-system/README.md).
**P-05 aprovada para planejamento em 28/10/2026:** [composições](compositions/README.md).
**P-06 documentada em 28/10/2026:** [roadmap e 18 cartões](tasks/README.md), todos não iniciados.
O mapa foi confirmado para o planejamento; não houve teste de descoberta com
participantes nem aceite funcional.

| Etapa | Trabalho | Entrega e critério de avanço |
| --- | --- | --- |
| P-01 — Inventário e preservação | Mapear dez rotas, tarefas, público/papéis, objetos, ações, estados e recursos existentes. Conferir código/testes relevantes, sem carregar todos os cartões B2. | Matriz página → tarefa → perfil → contexto → comportamento a preservar, com arquivos e evidências identificados. |
| P-02 — Arquitetura da informação | Definir grupos, nomes, navegação global/local, entradas diretas, contexto compartilhado e diferenças entre operação, jobs e área pública. | Mapa proposto com todas as funções localizáveis, relação com as rotas atuais e decisão explícita sobre nomes/URLs. |
| P-03 — Avaliação dos caminhos | Percorrer cenários, revisar heurísticas e preparar teste da árvore de navegação. Conduzir com participantes somente quando disponíveis; não simular sua participação. | Problemas, ajustes e confirmação do mapa pelo usuário. Distinguir revisão do agente, revisão do usuário e teste com participantes. Se não houver participantes, registrar a limitação. |
| P-04 — Design system planejado | Aproveitar tokens/componentes atuais; especificar fundamentos, componentes/estados, gráficos, layouts, redação e linguagem visual/interativa do 3D. | Referência aprovada com exemplos e regras de uso; cada regra identifica o que já existe e o que será alterado. Não apresentar especificação futura como sistema implementado. |
| P-05 — Composições e estratégia 3D | Especificar desktop/mobile, estados críticos e aplicação do sistema às famílias de página. Definir alternativas de geometria/asset, câmera, materiais, rótulos, licença/origem e orçamento a medir. | Composições revisadas, diferenças em relação à imagem anotadas e experimento futuro de viabilidade 3D delimitado. Render interativo, alterações de código e medição de desempenho ficam para implementação autorizada. |
| P-06 — Roadmap retomável | Dividir a implementação pelo mapa e sistema definidos; separar fundação, migração das páginas, 3D, regressão e fechamento. | Índice e cartões locais com dependências, leitura mínima, escopo, aceite, validação e checkpoint. Experimento 3D cedo no percurso de implementação. |

A implementação depende de autorização específica posterior; concluir P-06 não
inicia tarefas técnicas. Nenhuma data de execução ou estimativa de duração foi fixada.

## Como fundamentar decisões

Para cada decisão importante registrar:

1. Problema e evidência: código, interface observada ou hipótese.
2. Fonte e princípio aplicável, com link do [registro de referências](references.md).
3. Proposta para o ColdSafe e alternativa relevante quando houver dúvida material.
4. Compromisso envolvido: contexto, esforço, descoberta, acessibilidade ou desempenho.
5. Como verificar e qual foi o resultado, sem preencher testes ainda não executados.

Guias e exemplos externos não comprovam a eficácia da proposta no ColdSafe.
Não alegar que a arquitetura foi validada com pessoas quando houve só revisão heurística.

## Questões que o mapa precisa resolver

- Monitoramento, análise preditiva e gêmeo são vistas relacionadas do mesmo
  equipamento? A proposta atual é tratá-las como navegação local de Monitoramento.
- Como conservar ambiente/dispositivo entre essas vistas, revalidar acesso e
  limpar seleção na troca de conta ou perda de permissão?
- Quais destinos cada papel pode consultar e quais ações pode executar?
  Visibilidade do menu não substitui autorização do backend.
- Como distinguir o contexto de equipamento ao vivo de dataset/job sintético?
- Onde manter Assistente, documentação existente e saída da conta sem inventar
  uma central de ajuda ou outras páginas ausentes?
- Como manter links diretos, voltar/avançar, foco e navegação móvel compreensíveis?
- Como entrar no produto sem dados ou equipamentos, ou em modo legado sem 3D?

## Regras a preservar

- Conexão, atualidade da leitura e atualidade da previsão são informações distintas.
- Leitura antiga não confirma situação atual; ausência não vira zero; zero válido permanece.
- Saúde/RUL são estimativas sintéticas do equipamento associado, sem garantia física
  ou previsão própria inventada para sensores/atuadores.
- Falha parcial não esconde os demais dados válidos; reconexão recupera o estado.
- Envio, ACK e estado observado do LED permanecem distintos; permissões preservadas;
  buzzer automático sem comando manual novo.
- Histórico por sensor mantém isolamento por IDs; atuadores sem série própria
  continuam com histórico contextual identificado, sem curva booleana inventada.
- Troca de escopo invalida respostas antigas; dados de uma conta não reaparecem em outra.
- Estados têm texto além da cor; gráficos mantêm resumo e tabela; teclado e foco
  participam de cada fluxo; movimento reduzido e fallback WebGL são preservados.
- Cena vence/congela pela atualidade mesmo conectada; movimento/temperatura visuais
  são ilustrativos; seleção não envia comando.
- Jobs continuam recuperáveis sem repetir geração/treino; assistente conserva
  cancelamento e resposta incompleta explícita; mídia pública identifica simulação.

## Limites da imagem aprovada

A [imagem](assets/gemeo-digital-conceito.png) orienta composição e acabamento.
Não é modelo 3D, fotografia do hardware, especificação completa ou teste de interface.
Sua origem e correção estão no [registro de referências](references.md#imagem-conceitual-aprovada).

O histórico do gêmeo fixa 15 minutos em `frontend/src/features/digital-twin/TwinItemPanel.vue`.
A P-05 preserva esse limite; quatro períodos pertencem ao dashboard. A imagem
conceitual anterior não autoriza estender esse contrato.
IDs, controle LED e estados que não cabem na composição não podem ser removidos.

## Forma dos cartões futuros

- ID, status, dependências e objetivo delimitado.
- Ler primeiro: referências indispensáveis e código a conferir na retomada.
- Escopo, exclusões e arquivos sob responsabilidade.
- Regras de produto e decisões visuais pertinentes, por referência curta.
- Passos pequenos e critérios de aceite observáveis.
- Testes planejados; ao encerrar, registrar separadamente os efetivamente executados.
- Resultado, arquivos criados/alterados, dependências, evidências e suas fronteiras.
- Limites, checkpoint e próxima ação escolhida pelo usuário.

Testes acompanham cada mudança: lógica nova relevante com teste primeiro,
regressões focadas, navegação/estados no navegador e verificação visual desktop/mobile.
Preservar a meta de cobertura do projeto nos módulos pertinentes; cobertura não
substitui inspeção visual, acessibilidade ou teste com pessoas.
Integração real só quando justificada, em ambiente apropriado e autorizado.
Não executar comandos históricos ou iniciar a pilha pessoal por reflexo.

## Registro da consolidação inicial

Criados somente documentos de planejamento e cópia da referência visual.
Nenhuma das seis etapas foi marcada como concluída, nenhum cartão técnico foi
iniciado e nenhuma dependência foi adicionada nessa consolidação inicial.

## Checkpoint P-01 — 27/10/2026

Inventário estático concluído com matriz das dez rotas, papéis de página/ação/API,
contextos e sua persistência, caminhos, estados e fontes/testes a preservar.
Detalhes e limites no [inventário](inventory.md). Nenhum teste funcional foi executado.
Próxima ação registrada naquele checkpoint: P-02; implementação permaneceu pendente.

## Checkpoint P-02 — 27/10/2026

Mapa proposto elaborado, com quatro destinos globais, navegação local, dez rotas
mantidas, rótulos candidatos, utilitários, regras de contexto/acesso e intenção
responsiva. Mudanças de parâmetros de contexto, marca interna e aviso de rascunho
estão identificadas como propostas futuras, não funcionalidades implementadas.
Fontes e critérios de avaliação ligados às decisões no [documento](information-architecture.md).
Próxima ação proposta: P-03, mediante escolha do usuário; confirmação do mapa,
design system detalhado, composições e implementação continuam pendentes.

## Checkpoint P-03 — 27/10/2026

Revisados 11 cenários e as dez heurísticas, com uma revisão documental independente.
Usuário confirmou agrupamentos e os nomes Saúde e previsões e Filas e mensagens.
Mapa atualizado com retomada explícita de job conhecido na aba, acesso pendente,
recuperação de links e ordem de resolução de rascunhos. Esses mecanismos são
propostos, não implementados. Resultado, respostas e protocolo ainda não aplicado
no [relatório](path-evaluation.md).

Verificados links locais, correspondência das dez rotas e formatação. Sem app,
build, testes funcionais, pesquisa com participantes ou dependências novas.
Próxima ação proposta: P-04, design system planejado, após escolha do usuário.

## Checkpoint P-04 — 27/10/2026

Entregue proposta v0.1 do [design system](design-system/README.md), com fundamentos,
catálogo de padrões, regras do gêmeo e pranchas estáticas. Reaproveita tokens/fonte
existentes, distingue componentes reais de padrões ainda locais e conserva o mapa
da P-03. Valores de layout e acabamento são propostas para revisar.

Calculados 20 pares de contraste dos temas existentes; conferência documental e
visual dos artefatos registrada no guia da P-04. Sem implementação do aplicativo,
dependências novas ou teste funcional. Naquele fechamento, aprovação ainda pendente;
P-05 e P-06 não haviam sido iniciadas. Próxima ação naquele momento: revisão do usuário.

## Checkpoint P-05 — 28/10/2026

O usuário aprovou a P-04 e escolheu a próxima etapa. Entregues composições das dez
rotas, desktop/celular, estados transversais em 320 px e especificações completas.
Estratégia 3D começa por geometria própria refinada, câmera fixa e pausa manual;
GLB é alternativa condicionada ao experimento futuro, com origem/licença e metas
de desempenho a conferir. Nenhum experimento foi executado agora.

Artefatos, verificação e limites no [guia da P-05](compositions/README.md).
Somente documentação/imagens; sem dependências novas ou alterações no aplicativo.
Próxima ação naquele fechamento: revisão do usuário sobre P-05. Após esclarecer
3D real, o usuário aprovou e escolheu P-06, sem iniciar implementação.

## Checkpoint P-06 — 28/10/2026

Criados índice e 18 cartões RD em [tasks](tasks/README.md), com dependências,
leitura mínima, escopo/arquivos, aceite, testes planejados e checkpoint. Experimento
3D no início; contexto, rascunhos e retomada separados das migrações visuais.
A decisão da RD-02 condiciona a produção da cena. As dez rotas continuam cobertas.

Verificações e limites no índice P-06; somente documentação alterada, sem
bibliotecas novas, implementação ou testes funcionais. Próxima ação: usuário
escolher uma tarefa, sugerida RD-01. Não avançar automaticamente.
