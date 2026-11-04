# P-03 — Avaliação dos caminhos

- **Status:** concluída em 27/10/2026 como revisão documental e confirmação dirigida.
- **Resultado:** usuário confirmou agrupamentos e os nomes Saúde e previsões e
  Filas e mensagens. [Mapa atualizado](information-architecture.md).
- **Método:** percurso de cenários pelo agente principal e revisão independente
  de outro agente; três perguntas de preferência/confirmação respondidas pelo usuário.
- **Limites:** sem aplicação executada, protótipo, teste funcional ou pesquisa com
  participantes. Ajustes de comportamento abaixo são especificações futuras.

## 1. O que esta avaliação permite concluir

A revisão confrontou a [P-02](information-architecture.md) com as tarefas,
permissões e contratos do [inventário](inventory.md). Cobertura documental significa
que uma regra foi especificada; não comprova que a interface funciona ou que as
pessoas encontrarão seu destino. Não foram atribuídas notas ou taxas de sucesso.

As [heurísticas de Nielsen](https://www.nngroup.com/articles/ten-usability-heuristics/)
fornecem critérios de revisão. Os ajustes concretos são decisões para o ColdSafe,
não conclusões de um estudo experimental sobre o produto.

O usuário já conhecia o mapa e recebeu opções de nomes. Suas respostas registram
preferência e aprovação de planejamento; não são teste independente de descoberta.
O [teste da árvore](https://www.nngroup.com/articles/tree-testing/) avalia localização
por tarefas na hierarquia e pode ocorrer sem a interface visual. O protocolo da
seção 5 está preparado, mas não foi aplicado.

## 2. Confirmação do usuário

Respostas recebidas na conversa em 27/10/2026:

| Pergunta dirigida | Resposta registrada | Consequência |
| --- | --- | --- |
| Nome da vista de condição estimada, tendência e vida útil restante | “Saúde e previsões” | Manter esse rótulo local em Monitoramento. |
| Nome do painel técnico de filas, processamento, consumidores e amostras | “Filas e mensagens” | Manter esse destino com explicação de infraestrutura. |
| Confirmar os quatro agrupamentos e Assistente/documentação como utilitários | “Confirmo os agrupamentos” | Mapa aprovado para o planejamento. |

Isso não aprova telas ainda não desenhadas, desempenho 3D ou implementação.
Os títulos Visão geral, Dados sintéticos e Treinamento de modelos integram o mapa
confirmado; sua compreensão por outros perfis permanece uma hipótese.

## 3. Percurso de cenários e ajustes

Todos os percursos abaixo foram examinados em documentos, não executados no app.
IDs C-01 a C-11 servem para rastrear verificações futuras, não são novos cartões.

| ID e intenção | Caminho esperado | Cobertura e consequência para a proposta |
| --- | --- | --- |
| C-01 — Entender quanto tempo o equipamento pode continuar operando | Monitoramento → Saúde e previsões | Caminho documentado. Explicar “Vida útil restante estimada”, unidade, origem sintética e indisponibilidade; temperatura normal não equivale a saúde global. |
| C-02 — Investigar leitura de uma peça | Monitoramento → Gêmeo digital → cena ou lista → item | Lista deve ser entrada reconhecível. Preservar mesmo ID, histórico de 15 min e identificação de série contextual; previsão do equipamento não vira previsão do sensor. |
| C-03 — Consultar cadastro como visualizador | Ambientes e dispositivos → ambiente/dispositivo | Consulta prevista, escrita negada. Estado vazio não oferece cadastro nem ação fictícia de pedir acesso; explicar o acesso necessário. |
| C-04 — Gerar dados, treinar, sair e retomar | Dados e modelos → Dados sintéticos → dataset concluído → Treinamento de modelos → retorno | Lacuna: URL recuperável não significa URL reencontrável no menu. Acrescentar acesso explícito de retomada, delimitado abaixo. |
| C-05 — Investigar atraso no processamento | Filas e mensagens → métricas/amostras | Rótulo confirmado com risco semântico. Mostrar subtítulo de infraestrutura; métricas globais e amostras privadas/efêmeras não têm o mesmo escopo. |
| C-06 — Pedir explicação ao Assistente | Utilitário Assistente → pergunta → conferência operacional | Escopo da conta e conversa local precisam estar visíveis antes da primeira pergunta. Identidade não vira link para página de perfil inexistente. |
| C-07 — Entrar enquanto acesso é verificado ou após revogação | URL → verificação → conteúdo permitido ou restrição | Precisar o estado pendente; nunca presumir viewer confirmado. Acesso revogado/401 tem prioridade sobre rascunhos e respostas atrasadas. |
| C-08 — Abrir link inválido ou inacessível | URL → validação → explicação e saída permitida | Par operacional já coberto. Estender regra explícita a job/dataset; não repetir POST, revelar recurso de terceiros ou trocar silenciosamente de alvo. |
| C-09 — Navegar em 320 px e com texto ampliado | Menu global rotulado → área → links locais completos | Intenção documentada; encaixe, foco e área do gêmeo dependem das composições P-05 e da verificação futura no navegador. |
| C-10 — Sair com regras/formulário alterado | Tentar mudar rota/escopo → permanecer ou descartar | Decisão vem antes de confirmar destino e limpar rascunho. Permanecer conserva valores e contexto; descartar efetiva uma transição. |
| C-11 — Navegar com comando LED pendente | Visão geral/Gêmeo → outra vista → retorno | Mesmo pedido e equipamento; retorno não reenvia comando. Estado não confirmado permanece explícito, sem inferir ACK pelo desenho da peça. |

### Ajustes delimitados da especificação

**A-01 — Reencontrar trabalho conhecido (C-04).** Conservar `/laboratory` como
entrada global e os links locais com seus destinos normais. Nas duas vistas de
Dados e modelos, prever ações secundárias “Retomar geração” e “Retomar treinamento”
quando existir referência de trabalho conhecido na sessão da aba. Guardar no máximo
uma referência por tipo, obtida por criação confirmada ou consulta autorizada;
compor apenas a rota/query permitida, sem guardar tokens, resultados ou URL externa.
O link consulta o job e sua relação com dataset pelas APIs existentes, sem POST.
Não é histórico completo, busca de jobs perdidos ou persistência entre sessões.

No retorno, revalidar identidade, acesso da página e recurso. Erro temporário de
consulta permite repetir GET e não apaga a referência como se o job não existisse.
Referência malformada ou definitivamente inacessível é descartada com explicação
genérica. Encerrar a sessão/logout ou trocar de conta limpa referências privadas;
navegar para outra página preserva as referências. Revogação limpa o que deixou
de ser permitido. Não mudar a política da API de GET por dono.
Envio incerto sem ID confirmado continua sem retomada garantida ou repetição automática.

**A-02 — Identidade pendente (C-07).** Durante verificação, exibir estado ocupado
e links das áreas comuns, sem conteúdo privado, escrita ou módulos administrativos.
Selecionar outro destino protegido mantém a verificação. Falha permite repetir a
consulta de identidade; não autoriza conteúdo nem se apresenta como revogação.

**A-03 — Links e rascunhos (C-08/C-10).** UUID malformado não inicia consulta;
recurso inexistente/inacessível recebe mensagem sem confirmar sua existência e
retorno ao destino permitido da área, sem novo envio. Se job e dataset coexistirem,
confirmar a relação pelo resultado autorizado antes de associá-los. Rota desconhecida
precisa de recuperação no shell/roteador futuro, sem criar uma 11ª página de produto.
Para edição não salva, resolver permanecer/descartar antes de efetivar a transição;
autenticação e revogação não ficam presas nesse aviso.

**A-04 — Clareza de conteúdo (C-01/C-03/C-05/C-06).** Manter nomes confirmados;
explicar a geração de dados sintéticos no título/propósito da página, a natureza
estimada da saúde/RUL e o escopo de infraestrutura. Tornar perceptível o descarte
da conversa ao sair, mesmo depois de uma resposta concluída. Não inventar catálogo
de modelos, solicitação de permissão ou perfil editável.

Esses ajustes foram incorporados à P-02 como propostas de comportamento. Aprovação
do mapa não equivale à implementação ou verificação desses mecanismos.

## 4. Aplicação das dez heurísticas

Critérios adaptados de UX-01 no [registro de fontes](references.md).
Esta matriz é uma leitura crítica da proposta, não uma auditoria visual concluída.

| Heurística | Aplicação ao ColdSafe e verificação futura |
| --- | --- |
| Visibilidade do estado | Expor equipamento, idade da leitura, job e ACK separadamente; verificar estados desconhecidos e atrasados. |
| Linguagem do usuário | Explicar vida útil restante e geração; verificar interpretação dos nomes confirmados. |
| Controle e liberdade | Permitir permanecer/descartar, voltar e retomar consulta; sair não cancela job remoto. |
| Consistência | Mesmos grupos no desktop/celular; mesma identificação entre as três vistas operacionais. |
| Prevenção de erros | Revalidar contexto e acesso; inspeção não atua e navegação não cria job. |
| Reconhecimento | Destino ativo, nomes completos e ação de retomada visíveis; não exigir memorizar UUID. |
| Eficiência | Conservar links diretos, queries e retorno; conferir teclado sem atalhos inventados. |
| Design essencial | Quatro áreas conforme papel e utilitários distintos; não replicar todos os controles em toda página. |
| Recuperação de erros | Explicar escopo inválido e permitir nova consulta/escolha; não converter ausência em zero. |
| Ajuda e documentação | Explicações junto das estimativas e ações; documentação da API identificada como técnica. |

A11Y-01/A11Y-02 acrescentam critérios de teclado, foco, reflow e alternativas ao 3D.
Menu mais curto e texto completo não bastam para declarar conformidade WCAG.

## 5. Protocolo preparado para teste da árvore

**Não executado.** Recrutamento e contato com participantes não foram realizados.
Selecionar pessoas compatíveis com consulta/operação e administração; registrar
papel, familiaridade com o projeto e eventual exposição prévia ao mapa. Não contar
agentes como participantes nem a confirmação da seção 2 como descoberta espontânea.

Aplicar uma tarefa por vez numa árvore textual neutra, mostrando só os destinos
permitidos ao perfil. Não apresentar gabarito, explicar a estrutura ou sugerir o
nome correto. Registrar a primeira escolha, percurso, recuos, destino final,
desistência e comentário com consentimento; tempo só se efetivamente medido.
Links diretos/retomada e interação móvel exigirão avaliação separada da árvore.

### Instruções para apresentar à pessoa

| Tarefa | Enunciado sem indicar o destino |
| --- | --- |
| T-01 | Você precisa estimar por quanto tempo um equipamento pode continuar funcionando. Onde procuraria? |
| T-02 | Você quer localizar uma peça do equipamento e conferir sua última medição. Onde começaria? |
| T-03 | Você quer conferir quais dispositivos estão registrados num ambiente. Onde procuraria? |
| T-04 — admin | Você precisa produzir uma base artificial para um experimento. Onde começaria? |
| T-05 — admin | Uma base já foi produzida e você quer usá-la para avaliar uma previsão. Onde procuraria? |
| T-06 — admin | O processamento parece atrasado; você quer conferir consumidores e acúmulo de eventos. Onde começaria? |
| T-07 | Você quer fazer uma pergunta em linguagem natural sobre os dados da sua conta. Onde iria? |

### Gabarito do facilitador — não apresentar antes das tarefas

T-01: Monitoramento → Saúde e previsões; T-02: Monitoramento → Gêmeo digital;
T-03: Ambientes e dispositivos; T-04: Dados e modelos → Dados sintéticos;
T-05: Dados e modelos → Treinamento de modelos; T-06: Filas e mensagens;
T-07: Assistente nos utilitários. Aceitar caminho alternativo coerente e registrar
sua interpretação; não classificar a pessoa como errada para proteger o mapa.

Consolidar dificuldades por tarefa, perfil e interpretação; ajustar hipótese
quando houver evidência. Uma rodada exploratória pequena não demonstra taxas gerais.
Sem participantes nesta etapa, não há resultados ou métricas a preencher.

## 6. Fechamento e retomada

- Criado este relatório; atualizados mapa, guia e plano. Nenhuma dependência nova.
- Revisão independente identificou principalmente retomada de job, ambiguidade de
  rótulos, identidade pendente e ordem de descarte; ajustes incorporados acima.
- Verificações desta entrega: 91 links/âncoras locais nos seis documentos, dez
  rotas correspondentes ao roteador/inventário, 11 cenários, coerência dos estados
  documentais e formatação. Não são testes do aplicativo.
- Mapa confirmado para planejar; descoberta por outros usuários, acessibilidade,
  comportamento real e viabilidade gráfica continuam sem validação.

**Próxima ação proposta:** P-04 — Design system planejado, após escolha do usuário.
Usar mapa e riscos deste relatório para especificar padrões; composições ficam na
P-05 e cartões na P-06. Nenhuma dessas etapas foi iniciada por esta entrega.
