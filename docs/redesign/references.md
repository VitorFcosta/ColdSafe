# Fontes, propostas e limites

Registro consolidado em 27/10/2026 a partir das consultas feitas nesta conversa.
Não é revisão sistemática da literatura. Artigos de orientação, guias oficiais e
exemplos não são estudos experimentais do ColdSafe nem provas de conformidade.
Nas retomadas, verificar a fonte antes de depender de detalhes que possam mudar.

## Arquitetura da informação e navegação

| ID | Fonte e tipo | Aplicação proposta | Limite |
| --- | --- | --- | --- |
| IA-01 | [NN/G — IA vs. Navigation](https://www.nngroup.com/articles/ia-vs-navigation/), orientação profissional | Definir tarefas, relações e nomes antes da aparência do menu. | Não prescreve o agrupamento específico do ColdSafe. |
| IA-02 | [NN/G — Local Navigation](https://www.nngroup.com/articles/local-navigation/), orientação profissional | Separar áreas globais de vistas relacionadas dentro do contexto de equipamento. | Agrupamento e rótulos precisam ser avaliados no produto. |
| IA-03 | [NN/G — Card Sorting vs. Tree Testing](https://www.nngroup.com/articles/card-sorting-tree-testing-differences/), guia de métodos | Agrupamento de cartões descobre categorias; teste da árvore avalia caminhos. | Ler o método não equivale a conduzir pesquisa com participantes. |
| IA-04 | [NN/G — Tree Testing](https://www.nngroup.com/articles/tree-testing/), guia metodológico | Preparar tarefas de localização sem dar o nome do destino. | Rodada qualitativa pequena não sustenta estatísticas gerais. |
| NAV-01 | [IBM Carbon — UI Shell Left Panel](https://www.carbondesignsystem.com/building-blocks/core/components/ui-shell-left-panel/guidelines), documentação oficial | Estrutura persistente e hierarquia curta. | Não importar biblioteca ou copiar dimensões por padrão. |
| NAV-02 | [PatternFly — Navigation](https://www.patternfly.org/components/navigation/design-guidelines/), documentação oficial | Navegação global/local consistente e adaptação móvel. | Menus em cascata e variantes disponíveis não justificam sua adoção. |
| NAV-03 | [Atlassian — Navigation System Layout](https://atlassian.design/components/navigation-system/layout), documentação oficial | Responsabilidades claras para cabeçalho, lateral, conteúdo e inspeção. | Não requer componentes React nem todas as opções de redimensionamento. |
| A11Y-01 | [W3C — Disclosure Navigation](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/), exemplo técnico | Planejar teclado, foco e abrir/fechar navegação com semântica adequada. | Exemplo não é certificação nem código automaticamente pronto para produção. |

## Heurísticas, acessibilidade e dados

| ID | Fonte | Aplicação |
| --- | --- | --- |
| UX-01 | [NN/G — Ten Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) | Critérios concretos de estado, consistência, reconhecimento, prevenção/recuperação de erros e ajuda contextual. |
| A11Y-02 | [W3C — WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Definir verificações pertinentes de contraste, cor, teclado, foco, reflow, toque, alternativas e mensagens. Sem conformidade integral presumida. |
| DATA-01 | [Carbon — Data Visualization](https://www.carbondesignsystem.com/building-blocks/data-visualization/overview) e [paletas](https://www.carbondesignsystem.com/building-blocks/data-visualization/color-palettes) | Diferenciar identificação de séries e estados; escolher gráficos pela pergunta do usuário. |
| DATA-02 | [Grafana — Dashboard Best Practices](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/) | Hierarquia do geral ao específico, títulos claros e aprofundamento. Sem copiar densidade de infraestrutura para formulários. |

## Complemento da P-04 — consultado em 27/10/2026

| ID | Fonte primária | Uso e limite |
| --- | --- | --- |
| DS-01 | [Carbon — Color guidelines](https://www.carbondesignsystem.com/building-blocks/foundations/color/guidelines) | Cores por função/camada; nomes e valores do ColdSafe permanecem os tokens locais. |
| A11Y-03 | [W3C — Contrast Minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) | Critério de texto e cálculo de contraste; tokens calculados não comprovam interface renderizada. |
| A11Y-04 | [W3C — Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) | Identificação de componentes/estados e gráficos essenciais; avaliar cores adjacentes no uso real. |
| A11Y-05 | [W3C — Target Size Minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Distinguir mínimo AA e exceções da escolha do produto por controles de 44 px. |
| A11Y-06 | [W3C — Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) | Critério de adaptação e exceções para conteúdo bidimensional; sem teste de reflow do app na P-04. |

## Complemento da P-05 — consultado em 28/10/2026

| ID | Fonte primária | Uso e limite |
| --- | --- | --- |
| A11Y-07 | [W3C — Pause, Stop, Hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) | Pausa do movimento ilustrativo do gêmeo; controle não comprova conformidade dos demais conteúdos automáticos. |
| 3D-01 | [Three.js — Loading 3D models](https://threejs.org/manual/pages/loading-3d-models.html) e [Khronos glTF](https://www.khronos.org/gltf/) | Alternativa glTF/GLB se geometria própria for insuficiente; nenhum modelo externo adotado. |
| 3D-02 | [Three.js — WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html) e [Cleanup](https://threejs.org/manual/pages/cleanup.html) | Contagem de recursos e descarte no experimento futuro; sem benchmark nesta etapa. |
| 3D-03 | [Poly Haven — License](https://polyhaven.com/license) | Referência de origem/licença de assets, sem download ou seleção de material/HDRI. |

Aplicação, decisões locais, metas propostas e prompt da ilustração em
[estratégia 3D](compositions/3d-strategy.md). As metas não são prescritas por essas fontes.

## Referências visuais e 3D

- [Asimov Academy](https://ds.asimov.academy/design-systems/asimov-design-system/design-system.html):
  presença e hierarquia na apresentação. Não transportar efeitos decorativos ao monitoramento.
- [Clarix](https://ds.asimov.academy/design-systems/clarix-design-system/design-system.html):
  composição editorial como referência comparada, sem adotar hologramas ou robô no produto.
- [NASA Open MCT](https://nasa.github.io/openmct/about-open-mct/): vistas relacionadas
  de telemetria; não reproduzir árvore profunda ou montagem livre de painéis.
- [Model Viewer — Annotations](https://modelviewer.dev/examples/annotations/index.html):
  pontos de seleção, rótulos e vistas; referência de interação, sem adoção da biblioteca.
- [Three.js — GLTFLoader](https://threejs.org/examples/webgl_loader_gltf.html):
  referência de materiais e iluminação; não copiar modelo/cenário nem presumir seu custo gráfico.
- [NASA Eyes](https://eyes.nasa.gov/apps/solar-system/): contexto e indicação temporal
  junto da cena; não adotar estética espacial ou densidade desse exemplo.

Não houve auditoria integral das referências. O motor e a base visual existentes
devem ser avaliados antes de escolher assets ou novas dependências.

## Evidências locais já identificadas

Estas são observações de código, não novos testes funcionais:

- `frontend/src/router/index.ts`: dez rotas atuais, com navegação autenticada separada
  de apresentação e entrada. A estrutura técnica de URLs não determina a arquitetura de UX.
- `frontend/src/views/FoundationView.vue`: navegação extensa e textos externos de
  histórico fixos em temperatura, apesar da seleção de grandeza.
- `frontend/src/views/DigitalTwinView.vue` e `InsightsView.vue`: seleções próprias,
  com inicialização pelo catálogo; preservar contexto entre vistas é proposta de mudança.
- `frontend/src/styles/tokens.css`: cores semânticas, Inter, espaços, raios e movimento
  já centralizados; o design system deve aproveitar essa base.
- `frontend/src/features/digital-twin/TwinItemPanel.vue`: histórico de 15 minutos,
  isolamento por ID, previsão associada e controle LED compartilhado.

A inspeção anterior nesta conversa usou dashboard com fixtures HTTP/WS em desktop
e celular; não demonstrou sensores físicos nem infraestrutura real. Suas medidas
de posição dos painéis são diagnósticos daquele cenário, não testes executados
nesta consolidação nem metas universais de layout.

## Imagem conceitual aprovada

[Abrir imagem](assets/gemeo-digital-conceito.png).

- Origem: geração por IA com a ferramenta integrada imagegen nesta conversa;
  aprovada pelo usuário em 27/10/2026 como direção visual.
- Arquivo original: `exec-9573ddb7-deea-4399-8b55-26b6c9cf5ebd.png`, conservado em
  `~/.codex/generated_images/01a179c2-d5a6-79d1-a991-67e6f65da7d7/`.
- Cópia local sem edição para preservar a referência entre retomadas.
- Brief de origem: interface desktop clara, Inter/petróleo, navegação agrupada,
  seis medições compactas, ventilador em três quartos, seleção/lista/painel,
  histórico e previsão identificados; valores explicitamente simulados.
- Correção aplicada na geração: texto do LED mudou para Ligado para corresponder
  ao brilho; marcador 5 foi associado à temperatura do motor e o 7 retirado do
  buzzer, mantendo seis marcadores de sensores e atuadores sem essa numeração.
- Forma, materiais, posições, valores e gráfico são ilustrativos. Não contém
  geometria 3D executável, comprovação de hardware ou validação de acessibilidade.

## Como classificar os resultados futuros

Registrar separadamente: decisão do usuário, proposta de design, evidência de
código, observação renderizada, revisão heurística, teste com participantes e
teste técnico. Evitar transformar uma recomendação de guia em resultado de estudo
ou uma aprovação estética em autorização para implementar.
