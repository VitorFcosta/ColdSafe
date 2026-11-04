# P-05 — Composições e estratégia 3D

**28/10/2026 · P-05 aprovada para planejamento pelo usuário.**
Implementação não iniciada. Aprovação inclui gêmeo 3D real; imagens são referências.

Aplicação do [design system](../design-system/README.md) ao
[mapa confirmado](../information-architecture.md). Dez rotas, duas composições
por rota e uma prancha de estados transversais. Os IDs M/S são referências de
planejamento; os cartões de implementação pertencem à P-06.

## Consultar

- [Caderno visual em PDF](../assets/compositions/coldsafe-composicoes.pdf): 11 páginas.
- [Especificação por página](page-specs.md): ordem completa, continuação e estados.
- [Estratégia do gêmeo](3d-strategy.md): escolha inicial, alternativa GLB, origem
  da ilustração e experimento futuro com critérios mensuráveis.

| ID | Rota e composição | Imagem | Fonte editável |
| --- | --- | --- | --- |
| M-01 | `/` — Apresentação | [PNG](../assets/compositions/01-apresentacao.png) | [SVG](../assets/compositions/01-apresentacao.svg) |
| M-02 | `/login` — Entrar/criar conta | [PNG](../assets/compositions/02-acesso.png) | [SVG](../assets/compositions/02-acesso.svg) |
| M-03 | `/dashboard` — Visão geral | [PNG](../assets/compositions/03-monitoramento.png) | [SVG](../assets/compositions/03-monitoramento.svg) |
| M-04 | `/insights` — Saúde e previsões | [PNG](../assets/compositions/04-saude-previsoes.png) | [SVG](../assets/compositions/04-saude-previsoes.svg) |
| M-05 | `/digital-twin` — Gêmeo digital | [PNG](../assets/compositions/05-gemeo-digital.png) | [SVG](../assets/compositions/05-gemeo-digital.svg) |
| M-06 | `/manage` — Ambientes e dispositivos | [PNG](../assets/compositions/06-ambientes-dispositivos.png) | [SVG](../assets/compositions/06-ambientes-dispositivos.svg) |
| M-07 | `/messaging` — Filas e mensagens | [PNG](../assets/compositions/07-filas-mensagens.png) | [SVG](../assets/compositions/07-filas-mensagens.svg) |
| M-08 | `/laboratory` — Dados sintéticos | [PNG](../assets/compositions/08-dados-sinteticos.png) | [SVG](../assets/compositions/08-dados-sinteticos.svg) |
| M-09 | `/training` — Treinamento de modelos | [PNG](../assets/compositions/09-treinamento.png) | [SVG](../assets/compositions/09-treinamento.svg) |
| M-10 | `/assistant` — Assistente | [PNG](../assets/compositions/10-assistente.png) | [SVG](../assets/compositions/10-assistente.svg) |
| S-01 | Estados comuns em 320 px, sem rota nova | [PNG](../assets/compositions/11-estados-transversais.png) | [SVG](../assets/compositions/11-estados-transversais.svg) |

O [índice de artefatos](../assets/compositions/index.json) registra nomes e rotas
para conferência das exportações; não configura o roteador do aplicativo.

## Como interpretar as imagens

Cada prancha M mostra um enquadramento inicial de desktop 1440 × 1024 e celular
390 × 1024, reduzidos proporcionalmente no caderno. S-01 mostra quatro quadros
de 320 px em escala 1:1: menu, rascunho, link inválido e identidade pendente.
As pranchas não são screenshots da aplicação, resultados de media queries ou
prova de responsividade. O PDF permite ampliar os textos vetoriais.

“Continua abaixo” é anotação da composição: conteúdo não enquadrado permanece
na ordem indicada em page-specs. Não é um novo componente fixo para cobrir a
página. Os blocos de variações sob os enquadramentos são estados alternativos,
não alertas simultâneos que devam ocupar a interface inteira.

Os exemplos autenticados completos usam perfil **administrador** para mostrar
todos os destinos. Visualizador/operador continuam sujeitos à matriz de acesso
da P-01 e ao mapa da P-02. Nomes, números, filas, métricas e resultados são
fictícios; não representam observação da conta. A imagem do equipamento é gerada
por IA e não comprova contagem, posição ou identidade física dos sensores.

## Decisões novas e diferenças da referência anterior

- Quatro áreas globais e vistas locais aplicadas; Assistente/documentação como
  utilitários. Sem Ajuda, perfil editável ou página adicional inventada.
- Desktop orienta por área/contexto; celular usa menu rotulado e ordem de leitura.
  A prancha S-01 explicita o comportamento visual de abertura e recuperação.
- Gêmeo começa com vista fixa em três quartos. Sem órbita/zoom, não há controle
  “Vista inicial” sem função. Histórico permanece 15 min; controles de quatro
  períodos pertencem ao dashboard. Pausa manual controla somente a animação.
- Materiais/luz orientados pela nova ilustração; geometria própria refinada é a
  primeira candidata. Viabilidade e fidelidade do resultado ainda serão medidas.
- Retomada explícita mostra somente trabalho conhecido da aba, conforme P-03.
  Não é catálogo ou busca de jobs; não recupera envio incerto sem ID confirmado.
- Composição pública usa cópia candidata alinhada ao inventário AIoT; revisão
  factual e preservação do conteúdo acadêmico são necessárias antes de publicação.

## Verificação e checkpoint

Revisão de preservação dos campos/ações e da cena existente realizada por agentes
em modo somente leitura. A revisão de acessibilidade levou ao controle local de
pausa da animação. O limite de geração foi reconferido no código: de 1.000.000 a
2.000.000 de linhas, preservado na especificação.

Verificação executada em 28/10/2026:

- 174 links/âncoras locais em 13 documentos Markdown conferidos, sem destino ausente.
- Índice das dez rotas, 11 SVGs e 11 PNGs de 1600 × 1450 conferidos; S-01 não cria rota.
- PDF conferido com 11 páginas, títulos correspondentes e tamanho consistente.
- Exportação no Chromium instalado, fonte Inter local incorporada; nenhum texto
  ultrapassou a largura declarada ou o enquadramento nos checks automáticos.
- Inspeção visual do conjunto e das páginas principais; ajustes de espaçamento
  dos valores no celular e idade da leitura nas três vistas de monitoramento.
- Cópia da ilustração conferida por SHA-256; pixels preservados em relação à saída
  original da ferramenta integrada. Arquivos Markdown sem espaços finais;
  `git diff --check` sem erro nas alterações rastreadas.

Essas verificações cobrem artefatos estáticos; não comprovam ausência de todas as
sobreposições, responsividade ou funcionamento. Sem app, build, testes funcionais,
leitor de tela, teste com participantes ou benchmark 3D nesta etapa. Nenhuma
dependência instalada; somente documentação e imagens do redesign alteradas.

Na entrega inicial, a P-05 aguardava revisão. Em 28/10/2026, após esclarecer que
será 3D real no navegador, o usuário confirmou: “então está aprovado e pode passar
de tarefa”. A P-06 foi escolhida e está documentada no [roadmap](../tasks/README.md).
Aprovação não comprova funcionamento, simulação física ou fidelidade/performance 3D.
Implementação continua pendente de escolha da tarefa.
