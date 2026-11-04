# P-02 — Arquitetura da informação proposta

- **Status:** concluída como proposta documentada em 27/10/2026.
- **Aprovação do mapa:** agrupamentos e rótulos confirmados pelo usuário na
  [P-03](path-evaluation.md), em 27/10/2026; não é validação com participantes.
- **Revisão P-03:** retomada de jobs, identidade pendente, links e rascunhos
  precisados abaixo; continuam propostas de comportamento, sem implementação.
- **Base:** [inventário P-01](inventory.md) e [referências](references.md).
- **Escopo:** grupos, nomes, destinos, contexto, acesso, fluxos e intenção responsiva.
- **Limites:** nenhuma rota, interface, permissão, contrato ou dependência alterada;
  nenhum protótipo executável, estudo com usuários ou teste funcional realizado.

Esta é uma proposta específica para o ColdSafe fundamentada em guias e código.
As fontes não estudaram este produto nem comprovam a eficácia destes nomes.
O mapa foi confirmado para o planejamento; isso não inicia a implementação.

## 1. Objetivo e estrutura

Separar o deslocamento entre áreas da troca de vistas sobre o mesmo equipamento.
Conservar as funções existentes e evitar uma navegação que reproduza apenas a
lista de arquivos/rotas. Os quatro destinos globais são agrupamentos confirmados,
não quatro novas páginas.

```text
Área pública
  Apresentação do projeto                         /
  Entrar / Criar conta                            /login

Aplicação autenticada
  Monitoramento                                   entrada: /dashboard
    Visão geral                                   /dashboard
    Saúde e previsões                             /insights
    Gêmeo digital                                 /digital-twin
  Ambientes e dispositivos                        /manage
  Dados e modelos                                 entrada: /laboratory
    Dados sintéticos                              /laboratory
    Treinamento de modelos                        /training
  Filas e mensagens                               /messaging

  Acessos utilitários
    Assistente                                    /assistant
    Documentação da API                           /docs (fora da SPA)
    Apresentação do projeto                        /
    Sair                                          ação existente
    RabbitMQ                                      somente diagnóstico habilitado
```

Navegação global: os quatro destinos principais e utilitários, em posições estáveis.
Navegação local: três links em Monitoramento e dois em Dados e modelos, junto ao
título/contexto. São links entre páginas com endereços próprios, ainda que recebam
aparência de abas; não manter todas as páginas/cenas montadas como painéis ocultos.
Lista de sensores e seleção de peça são controles de inspeção, não outro nível do menu.

## 2. Relação com as dez rotas existentes

| Rota mantida | Rótulo atual | Rótulo/título proposto | Posição e entrada |
| --- | --- | --- | --- |
| `/` | Apresentação | Apresentação do projeto | Área pública; entrada direta e utilitário da aplicação. |
| `/login` | Entrar / Criar conta | Entrar / Criar conta | Página pública com os dois modos existentes; não criar rota de cadastro. |
| `/dashboard` | Monitoramento | Visão geral, dentro de Monitoramento | Destino padrão do link global Monitoramento e da marca interna. |
| `/insights` | Insights | Saúde e previsões | Segundo link local de Monitoramento. |
| `/digital-twin` | Gêmeo digital | Gêmeo digital | Terceiro link local de Monitoramento; requisitos de modo/3D explícitos. |
| `/manage` | Ambientes e dispositivos | Ambientes e dispositivos | Destino global direto, inclusive consulta do visualizador. |
| `/laboratory` | Laboratório | Dados sintéticos | Primeiro link local e entrada padrão de Dados e modelos. |
| `/training` | Treinamento | Treinamento de modelos | Segundo link local de Dados e modelos; preservar parâmetros de dataset/job. |
| `/messaging` | Mensageria | Filas e mensagens | Destino global direto; subtítulo identifica infraestrutura. |
| `/assistant` | Assistente | Assistente | Link utilitário permanente para a página existente. |

Não renomear caminhos nem exigir redirecionamentos para URLs novas nesta proposta.
Entrada padrão só vale ao acionar explicitamente o destino global; abrir/retomar
uma URL específica conserva sua página e parâmetros, sem passar pela entrada do grupo.
Não criar uma tela inicial de frota com contagens/resumos indisponíveis na API.

### Rótulos e promessas de conteúdo

- Visão geral é **do equipamento selecionado**, não da frota inteira.
- Saúde e previsões reúne estimativas, tendência, alertas e regras atuais. Deve
  manter a explicação de saúde/RUL sintéticas e seus estados de indisponibilidade.
- Dados sintéticos descreve geração, configuração, job e dataset; não é catálogo
  de medições reais nem editor de arquivos genérico.
- Dados e modelos reúne gerar dados e treinar/avaliar; não promete registro,
  ativação ou gerenciamento visual de versões que a interface não possui.
- Filas e mensagens tem subtítulo **Infraestrutura de processamento**; não é chat,
  central de notificações ou histórico durável das mensagens.
- Documentação da API mantém esse nome; não chamá-la de Ajuda ou Central de suporte.

Os nomes integram o mapa confirmado na P-03; sua compreensão por outros perfis
ainda precisa ser avaliada. A alteração é de rotulagem/navegação, sem mudar o
significado de estados ou criar funcionalidades implícitas. No conteúdo, explicar
“Vida útil restante estimada” e a geração de dados sintéticos sem depender de siglas.

## 3. O que ocupa cada região

| Região | Responsabilidade proposta |
| --- | --- |
| Navegação global | Mudar de área; destino atual marcado além da cor. Evitar repetir links locais também como oito destinos globais. |
| Cabeçalho da página | Título, propósito curto e contexto pertinente àquela área. Não impor seletor de equipamento a jobs, infraestrutura ou Assistente. |
| Navegação local | Mostrar a vista atual e as irmãs da mesma área, com nomes completos. |
| Conteúdo principal | Executar a tarefa da página; não exigir o mesmo painel de cartões em todos os módulos. |
| Inspeção contextual | Detalhes de item selecionado, sem confundir seleção com envio de comando. No gêmeo, cena/lista/painel permanecem ligados ao mesmo ID. |
| Utilitários | Acesso ao Assistente, documentação, apresentação e logout; não misturar com funções de monitoramento. |

Marca na aplicação autenticada propõe voltar a `/dashboard`, preservando contexto
válido. Marca na apresentação/entrada permanece ligada a `/`. Essa mudança em
relação ao comportamento atual fica explícita; apresentação continua alcançável.
Sem nova página Conta: conservar a ação Sair e identidade/perfil quando disponíveis.

Documentação da API e RabbitMQ propõem abrir em nova aba, com indicação textual,
para não desmontar o trabalho atual. RabbitMQ conserva a condição de diagnóstico
existente; não vira módulo comum ou controle de filas dentro da aplicação.

## 4. Contexto e navegação operacional

Proposta de mudança em relação à P-01: compartilhar **ambiente + registro do
dispositivo** somente entre `/dashboard`, `/insights` e `/digital-twin`.
Resolver MQTT ID, equipamento e componentes pelo catálogo/resumo autorizado.
Compartilhar identificação não significa compartilhar um snapshot como dado atual:
cada vista recupera/revalida o estado conforme seus contratos.

### Endereço, sessão e precedência

Proposta de parâmetros de navegação frontend nessas três rotas:
`?environment=<UUID>&device=<UUID-do-registro>`. São novos parâmetros propostos,
não parâmetros já implementados; não alteram a API nem são o MQTT ID.
Não incluir tokens, papel da conta ou valores de sensores no endereço.

1. Identidade e catálogo precisam ser confirmados antes de aplicar o par solicitado.
2. Par explicitamente informado na URL tem prioridade, se pertencer ao escopo atual.
   Par parcial, malformado, incompatível, inativo ou indisponível não deve trocar
   silenciosamente para outro equipamento: explicar indisponibilidade e oferecer
   escolha autorizada. Não revelar recursos de outra conta.
3. Sem par na URL, tentar o par salvo da sessão da aba e revalidá-lo. Se deixou de
   ser válido, avisar e pedir nova escolha em vez de conservar dado de outro escopo.
4. Na primeira entrada sem preferência, pode conservar o padrão atual do primeiro
   par autorizado disponível, com seus nomes visíveis; catálogo vazio tem estado
   próprio, sem dados demonstrativos misturados à operação.
5. Seleção confirmada atualiza o contexto compartilhado e o endereço da vista ativa;
   links para as outras duas vistas carregam o mesmo par validado. Não navegar ou
   atualizar simultaneamente três páginas. O par deve ser coerente; troca de
   ambiente invalida dispositivo anterior antes de mostrar dados.

URL/contexto são uma alteração funcional futura e precisam de cartão/testes próprios.
A implementação deve reaproveitar o armazenamento da aba quando adequado, sem criar
estado global entre contas, sincronização entre abas ou store nova por pressuposto.

### Limites da persistência

- A navegação local carrega o mesmo par validado. Retorno de outra área recupera
  esse contexto se continuar autorizado; logout/troca de conta limpa a preferência.
- Período do dashboard conserva a persistência existente. Não impor o mesmo
  período ao gêmeo de 15 min; os quatro períodos da imagem continuam decisão
  específica futura. Métrica e seleção de peça não ganham persistência por inferência.
- Peça selecionada é local ao gêmeo; mudança de equipamento/sessão limpa seu painel.
- Links de Visão geral para previsão/gêmeo podem carregar o par. Links genéricos
  do Assistente para Insights continuam sem presumir um equipamento, pois a pergunta
  pode tratar de vários itens da conta.
- Voltar/avançar deve restaurar a rota e o par explícito, revalidando acesso. Mudança
  intencional de equipamento gera uma entrada coerente de histórico; polling,
  relógios e revalidações não geram entradas nem saltos de foco. Seleção validada
  pode normalizar o endereço sem criar entrada duplicada.

## 5. Outros contextos e trabalho em andamento

| Área/situação | Regra de navegação proposta |
| --- | --- |
| Gestão | Seleção e formulários próprios. Links para `/manage` permanecem genéricos; o usuário confere/escolhe o ambiente nessa página. Gestão não herda automaticamente o par das três vistas operacionais. Um futuro atalho contextual exigiria contrato/tarefa próprios. Não salvar cadastro só por navegar. |
| Geração/treino | `?job=UUID` e `/training?dataset=UUID` existentes permanecem. Entrada direta não apaga parâmetros; recarga consulta o trabalho, sem repetir POST. Dataset fora da lista inicial limitada continua consultável pelo fluxo existente. |
| Job em execução | Navegar não cancela o job remoto. Não usar confirmação genérica de saída como se a execução fosse perdida; manter endereço e acesso de retomada descrito abaixo. |
| Formulário alterado | Antes de efetivar troca de rota/escopo ou voltar/avançar com edição não salva, resolver permanecer ou descartar. Permanecer conserva valores e contexto; descartar confirma uma transição e limpa o rascunho pertinente. É comportamento novo, sem autosave nem confirmação em toda navegação. |
| Comando de LED pendente | Navegar não significa cancelar, confirmar ou reenviar atuação. Ao retornar, recuperar estado autorizado do pedido e observação; seleção de peça nunca envia comando. |
| Assistente | Link permanente abre a mesma página. Sair conserva o contrato de apagar conversa local e interromper stream pendente; explicar esse ciclo antes da primeira pergunta, inclusive perda de conversa já concluída, com aviso se estiver respondendo. Não transformar em chat persistente no shell. |
| Infraestrutura | Não herdar filtro de equipamento. Separar métricas globais, amostras privadas/efêmeras, idade da consulta e atualidade do observador. |

**Ajuste P-03 — reencontrar job conhecido:** entrada global de Dados e modelos
continua em `/laboratory`; links locais conservam seus destinos normais. Nas duas
vistas, prever ações secundárias de retomar geração/treinamento quando a sessão
da aba tiver referência confirmada por criação ou consulta autorizada. No máximo
uma por tipo; limpar ao encerrar a sessão/logout ou trocar de conta, preservar
ao navegar para outra página e revalidar acesso no retorno. Não guardar resultados
ou tokens nem criar histórico completo, endpoint ou POST de
retomada. Erro transitório permite repetir GET; referência malformada ou
definitivamente inacessível é removida com explicação. Detalhes e limite para envio
incerto sem ID estão em [A-01 da P-03](path-evaluation.md#ajustes-delimitados-da-especificação).

Job/dataset inválido ou inacessível recebe recuperação sem revelar recurso de
terceiros nem reenviar operação. Havendo ambos na URL, confirmar sua relação por
consulta autorizada. Rota desconhecida precisa de recuperação futura no shell,
sem nova página de produto; a apresentação exata fica para P-05/implementação.

Expiração/revogação/limpeza de conta não podem ser bloqueadas por um aviso de
rascunho nem conservar texto privado da sessão anterior. O detalhe das interações
de aviso será desenhado na P-05 e testado na implementação.

## 6. Perfis, indisponibilidade e primeiro acesso

Esta proposta altera apresentação da navegação, não autorização. Políticas e
diferenças UI/API da [P-01](inventory.md#2-perfis-página-ação-e-política-da-api)
continuam vigentes.

| Estado/perfil | Navegação e conteúdo propostos |
| --- | --- |
| Visitante | Apresentação e entrada; acesso direto a página protegida mantém destino para login, com validação do redirecionamento interno existente. |
| Identidade em confirmação | Mostrar estado ocupado e links das áreas comuns, sem conteúdo privado, escrita ou módulos administrativos. Mudar destino protegido mantém verificação. Falha permite repetir consulta de identidade; não equivale a viewer confirmado nem a revogação. |
| Visualizador | Monitoramento, consulta de ambientes/dispositivos e Assistente; nenhum comando ou edição. Dados/modelos e filas seguem bloqueio administrativo atual das páginas. |
| Operador | Mesmas consultas, com escrita já permitida em catálogo/limites/regras e LED; sem acesso administrativo novo. |
| Admin | Quatro destinos globais e utilitários; ações conforme os contratos existentes. |
| Acesso direto a módulo restrito | Estado de acesso restrito e saída para área permitida; não apagar o motivo por redirecionamento silencioso. Não mostrar resultado privado enquanto papel não foi confirmado. |
| 401/troca de conta | Limpar contexto e conteúdo da sessão afetada, preservar proteção contra resposta atrasada e encaminhar ao acesso conforme comportamento existente. |
| Papel/acesso revogado | Limpar dados/ações não permitidos e explicar. A ocultação de links acompanha a política da página; GET privado por dono não passa a exigir admin por este documento. |
| Sem ambiente/dispositivo | Estado vazio com caminho para gestão; usuário sem escrita recebe orientação compatível com seu papel, sem botão de cadastro ou ação fictícia de pedir acesso. Sem medição zero ou equipamento fictício. |
| Gêmeo em modo legado | Identificar requisito AIoT junto ao destino; o link direto continua explicando indisponibilidade, sem cena inventada ou bloqueio das outras vistas. |
| WebGL indisponível | Manter inspeção/lista e dados acessíveis; erro gráfico não torna o equipamento indisponível por si só. |

Nenhuma permissão de criar/ativar modelos, controlar motor/buzzer, purgar/reentregar
filas ou gerenciar contas foi acrescentada pela organização dos destinos.

## 7. Desktop, celular e orientação

- Desktop: navegação global lateral; local junto ao título/contexto; utilitários
  identificados. Evitar hierarquia maior que a necessária; sem submenu em cascata.
- Em largura insuficiente: menu global pode virar painel sobreposto acionado por
  botão rotulado. Abrir leva foco ao menu; fechar por botão/Escape retorna ao
  acionador; seleção fecha menu e dá orientação à página. Se modal, fundo não
  pode receber foco. Detalhar comportamento/semântica no design system.
- Manter os mesmos grupos e nomes no celular. Três links locais podem quebrar em
  linhas organizadas com texto completo; não prometer encaixe numa linha em 320 px
  nem depender de rolagem horizontal pouco perceptível. Verificação visual na P-05.
- Link ativo usa texto/forma além da cor. Navegação funciona por teclado; não
  depende de hover ou de interpretar somente ícones. Preservar link de salto e foco.
- Cabeçalhos/painéis não devem ocultar foco ou cobrir comandos; detalhes do gêmeo
  entram na ordem de leitura móvel. Escolher peça não toma foco de forma inesperada.
- Atualização live não muda página, seleção ou foco. Reflow/ampliação, teclado,
  contraste e movimento reduzido serão verificados; este documento não declara WCAG.
- Hierarquia curta dispensa uma trilha longa de breadcrumbs. Título da área,
  link local ativo e equipamento identificado devem orientar; detalhes podem ter
  retorno contextual quando necessário, sem introduzir mais níveis fictícios.

## 8. Fluxos principais para detalhar e avaliar

Estes são caminhos propostos, não percursos executados nem testes de usuários.

| Intenção | Caminho | Condição de preservação |
| --- | --- | --- |
| Acessar um destino protegido | URL específica → login → mesmo destino. | Query de contexto/job não perdida; autenticação e acesso revalidados. |
| Investigar equipamento | Monitoramento → Visão geral → Saúde e previsões → Gêmeo digital. | Mesmo ambiente/dispositivo; cada vista mostra seu estado/atualidade. |
| Consultar um sensor | Gêmeo → cena ou lista → mesmo item/ID → histórico correspondente. | ID/isolamento preservados; seleção não comanda; atuador sem série própria identificado. |
| Corrigir cadastro/limites | Ambientes e dispositivos → ambiente → dispositivo/regras. | Viewer consulta; operador/admin alteram; rascunhos/confirmar desativação mantidos. |
| Produzir e avaliar dados | Dados e modelos → Dados sintéticos → dataset concluído → Treinamento de modelos. | Dataset/job privados, retomada sem POST, pacote não ativado por conclusão. |
| Investigar processamento | Filas e mensagens → métricas/amostras. | Admin; diferença entre agregação global e amostra privada/efêmera explícita. |
| Pedir explicação | Assistente → pergunta explícita → conferência em Insights/Monitoramento. | Escopo da conta, texto incompleto/erro e ciclo de vida local visíveis. |

## 9. Rastreabilidade das decisões

IDs de fontes correspondem ao [registro de referências](references.md).

| Decisão proposta | Problema do inventário | Fundamento | Verificação posterior |
| --- | --- | --- | --- |
| D-01: global por área + local por vistas | Oito destinos equivalentes misturam tarefas relacionadas e administrativas. | IA-01/IA-02, NAV-01/NAV-02: organização antes do menu, orientação local e hierarquia curta. | Localizar funções sem conhecer os módulos; conferir dez rotas sem função órfã. |
| D-02: nomes descritivos | Insights/Laboratório/Mensageria exigem interpretação. | UX-01: linguagem compreensível e reconhecimento. | Preferência e mapa confirmados na P-03; descoberta por outros perfis ainda não testada. |
| D-03: contexto operacional compartilhado | Seleções independentes entre três vistas do equipamento. | IA-02/UX-01 e fontes locais de sessão: consistência e orientação. | Navegar/voltar/recarga; invalidar seleção sem trocar equipamento silenciosamente. |
| D-04: contexto por família | Conta, equipamento, dataset/job e infraestrutura são diferentes. | IA-01/NAV-03 e matriz P-01. | Cabeçalho/filtro nunca sugere um escopo que a consulta não aplica. |
| D-05: acesso explícito por perfil | Página administrativa e GET por dono têm políticas distintas. | Evidência local da P-01; UX-01: estado/prevenção de erro. | Identidade pendente, viewer, operador/admin, URL direta e revogação. |
| D-06: links/retomada preservados | Jobs e seleção já têm persistência parcial. | UX-01: controle e recuperação; contratos atuais inventariados. | Query mantida, acesso de retomada de job conhecido, GET recuperável e nenhum POST causado por navegação. |
| D-07: adaptação sem perda de nomes | Navegação extensa e rótulos longos em celular. | NAV-02/NAV-03, A11Y-01/A11Y-02. | Teclado, foco, 320 px/texto ampliado; comparação visual na P-05. |
| D-08: utilitários sem novas funções | Marca, docs e Assistente têm destinos/ciclos próprios. | NAV-01/NAV-03, UX-01 e inventário local. | Apresentação alcançável, docs identificadas, conversa não tratada como persistente. |

O princípio da fonte fundamenta a decisão; não determina esses quatro destinos,
o rótulo Saúde e previsões ou o contrato de contexto. O mapa foi confirmado pelo
usuário; os mecanismos de contexto continuam especificações futuras a verificar.

## 10. Entrega, limites e retomada

- Criado este mapa com dez rotas preservadas, nomes candidatos, padrões de
  navegação, regras de contexto/acesso e fluxos; guia/plano atualizados.
- Revisão documental independente identificou cuidados de contexto, acesso
  pendente, rascunhos e nomes longos; incorporados antes do fechamento. A revisão
  do documento também precisou a atualização do endereço apenas da vista ativa
  e a manutenção de seleção própria na Gestão.
- Verificações: correspondência das dez rotas, links locais, formatação e
  cobertura das questões da P-02. Não representam aceite funcional ou validação com pessoas.
- Sem app/build/testes, novas composições/imagens, bibliotecas, mudança de
  código, endpoints, URLs implementadas ou permissões. No fechamento original
  da P-02, o mapa ainda não estava aprovado.

**Checkpoint atualizado pela P-03:** mapa confirmado em revisão dirigida;
relatório, ajustes e protocolo não aplicado em [Avaliação dos caminhos](path-evaluation.md).
Não houve teste de descoberta com participantes. Próxima etapa proposta é P-04,
design system planejado, após escolha do usuário; composições e código permanecem
nas etapas posteriores.
