# Fundamentos — P-04

**v0.1 de 27/10/2026, aprovada para planejamento em 28/10/2026.** Valores existentes abaixo foram lidos de
[tokens.css](../../../frontend/src/styles/tokens.css); regras de aplicação são
propostas. Não foram alterados tokens do aplicativo.

## F-01 — Cor por finalidade

Usar o nome semântico da função. Petróleo identifica ações/seleção; verde indica
condição favorável somente quando o domínio a confirma. Seleção, atualidade e
condição do equipamento são informações diferentes.

Todos os nomes na tabela têm prefixo `--cs-`. Os dois temas já existem; a coluna
escura corresponde a `.presentation-theme`, não a um novo alternador de tema.

| Token existente | Aplicação proposta | Claro | Apresentação |
| --- | --- | --- | --- |
| color-canvas | Fundo da página | `#f3f6f5` | `#081b20` |
| color-surface | Superfície principal | `#ffffff` | `#102a30` |
| color-surface-muted | Região secundária/seleção com indicador adicional | `#e9f0ee` | `#17373d` |
| color-ink | Texto principal | `#122e33` | `#edf6f3` |
| color-ink-muted | Texto secundário legível | `#526c70` | `#a8bfbd` |
| color-line | Separador decorativo | `#cbd8d6` | `#345057` |
| color-control-border | Limite identificável de campo/controle | `#687e7e` | `#829b9e` |
| color-accent | Ação primária, link e seleção | `#0c6d65` | `#9bf1d9` |
| color-accent-hover | Realce da ação ao apontar | `#07564f` | `#b7f9e8` |
| color-accent-ink | Texto sobre ação primária | `#ffffff` | `#0b302e` |
| color-status-normal | Condição favorável confirmada pelo domínio | `#176740` | `#9de0b3` |
| color-status-attention | Atenção | `#8b4c0c` | `#f2c27f` |
| color-status-critical | Condição crítica/erro, distinguida por texto | `#b02d24` | `#ffa69b` |
| color-status-stale | Dado antigo/desconhecido, distinguido por texto | `#536675` | `#bdcbd4` |
| color-normal-surface | Fundo de condição favorável | `#e5f1e9` | `#143d2d` |
| color-attention-surface | Fundo de atenção | `#fff1dc` | `#45351b` |
| color-critical-surface | Fundo crítico/erro | `#fcece8` | `#462825` |
| color-stale-surface | Fundo de dado antigo/desconhecido | `#e9eef2` | `#273a46` |
| focus-ring | Contorno de foco | `#086c68` | `#b7f9e8` |

Separador suave não serve como única borda de campo. Seleção usa fundo discreto,
contorno/marca petróleo e texto; não depende só da diferença de fundo. Não aplicar
opacidade ao bloco inteiro de leitura antiga: texto e aviso precisam permanecer legíveis.

## F-02 — Contraste verificado e critérios

Cálculo sobre cores opacas dos tokens, em sRGB, feito em 27/10/2026. Cada linha
tem dois pares medidos, total de 20. Não são amostras de pixels do aplicativo.

| Par | Claro | Escuro |
| --- | --- | --- |
| ink / surface | 14,34:1 | 13,67:1 |
| ink-muted / surface | 5,62:1 | 7,77:1 |
| ink-muted / canvas | 5,17:1 | 9,14:1 |
| accent-ink / accent | 6,19:1 | 10,82:1 |
| control-border / surface | 4,31:1 | 5,11:1 |
| focus-ring / surface | 6,26:1 | 12,70:1 |
| status-normal / normal-surface | 5,93:1 | 7,92:1 |
| status-attention / attention-surface | 6,01:1 | 7,20:1 |
| status-critical / critical-surface | 5,64:1 | 7,03:1 |
| status-stale / stale-surface | 5,10:1 | 7,11:1 |

Meta de texto comum: ao menos 4,5:1; componentes/gráficos essenciais: 3:1 contra
cores adjacentes, conforme casos aplicáveis de
[contraste de texto](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
e [não textual](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
Novas combinações, hover, sobreposições e imagens exigem nova conferência.
Não inferir contraste de todos os estados a partir desta tabela.

## F-03 — Tipografia

Inter local e números tabulares já existem no [estilo global](../../../frontend/src/styles/index.css).
Conservar a família e os arquivos existentes; nenhuma fonte remota adicional.
A escala abaixo usa tamanhos existentes, com papéis/pesos/entrelinhas propostos.

| Papel | Tamanho / entrelinha | Peso | Uso |
| --- | --- | --- | --- |
| Título operacional | 32 / 40 px | 650 | Um título principal por página; 24 / 32 em espaço estreito. |
| Seção | 20 / 28 px | 650 | Gráfico, formulário e agrupamento de conteúdo. |
| Corpo/campo | 16 / 24 px | 400 | Instrução, texto digitado e conteúdo principal. |
| Rótulo/ação | 14 / 20 px | 600 | Labels, navegação, botão e cabeçalho de tabela. |
| Metadado | 14 / 20 px | 400 | Horário, origem, ID, versão; 12 / 16 só em nota auxiliar. |
| Medição principal | 48 / 56 px | 650 | Um valor prioritário; 32 / 40 em conjunto compacto. |
| Título público | 48 / 56 ou 64 / 72 px | 650 | Apresentação, com adaptação ao conteúdo/espaço. |

Converter tamanhos tipográficos em rem na implementação. Texto pode crescer;
nenhuma altura fixa recorta labels ou mensagens. Unidade fica junto do valor,
com peso menor quando útil, sem virar nota ilegível. IDs longos quebram; dados
essenciais não dependem de reticências/tooltip. Monoespaçada atual só para IDs/
amostras técnicas onde ajude. Não usar caixa alta para parágrafos ou menu inteiro.

## F-04 — Espaço, forma e densidade

Escala existente: 0, 4, 8, 12, 16, 24, 32, 48, 64 e 96 px. Aplicação proposta:
4 entre fragmentos relacionados; 8 entre label/controle; 12 entre ações;
16 em grupos compactos; 24 no interior de painéis; 32 entre seções; 48–96
para composição pública. Em celular, painéis podem usar 16 para preservar área útil.

Raios existentes: 4, 8 e 16 px. Proposta: 4 em indicadores compactos; 8 em campos,
botões e painéis; 16 reservado a superfícies amplas de apresentação. Não criar
nomes `radius-sm/lg` presumindo que existam: o código de treinamento contém usos
sem definição no arquivo de tokens conferido; a migração futura deverá reconciliá-los.

Sombra de painel existente: `0 2px 8px rgb(18 46 51 / 0.03)`, apoio discreto.
Separação vem principalmente de espaço, superfície e hierarquia. Menus/diálogos
precisam de camada clara; não multiplicar cartões e sombras para todo dado.

Controles comuns: mínimo proposto de 44 px de altura e alvo de ícone 44 × 44 px;
padding horizontal 16, texto 14/20. É escolha de conforto do ColdSafe. A WCAG 2.2
AA define alvo mínimo de 24 × 24 CSS px ou condições de exceção/espaçamento;
não atribuir a ela a regra de 44 px.
[Fonte](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
Tabelas podem ser compactas sem reduzir a área das ações nelas presentes.

## F-05 — Composição e adaptação propostas

| Região | Ponto de partida para P-05 |
| --- | --- |
| Estrutura autenticada | Lateral de 256 px quando houver espaço; conteúdo com respiro de 32 px, 16 em celular. |
| Menu compacto | Abaixo de 64 rem, partir de botão Menu + painel sobreposto; ajustar pela composição real, não pelo nome do dispositivo. |
| Conteúdo | Área útil até 1600 px; formulários até 720 px e texto corrido próximo de 65 caracteres por linha. |
| Inspeção do gêmeo | Detalhe entre 320–360 px ao lado de cena com área suficiente; empilhar quando conteúdo disponível for menor que 960 px. |
| Navegação local | Links com nomes completos e quebra de linha; sem esconder destino atrás de rolagem imperceptível. |
| Ordem móvel | Título/contexto → links locais → estado/resumo → tarefa principal → detalhes relacionados. |

Essas dimensões são propostas verificáveis, não medições do app ou garantia de
encaixe. Cabeçalhos não devem ocupar todo o primeiro viewport nem cobrir o foco.
Conferir 320 CSS px, ampliação de texto e zoom; rolagem bidimensional fica restrita
a conteúdo que a exige, como tabela, com região identificada e acessível.
[Reflow — W3C](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
Composições completas por página pertencem à P-05.

## F-06 — Foco, movimento e redação

Conservar foco global de 3 px com afastamento de 3 px; verificar contraste sobre
cada fundo e ausência de recorte. Navegação/seleção ativa e foco são estados distintos.
Link de salto e ordem de leitura permanecem funcionais. Nenhum dado depende de hover.

Tempos existentes: 160 ms rápido, 240 ms padrão, 560 ms entrada. Proposta: primeiro
para resposta visual de controle, segundo para abertura/fechamento discreto;
entrada longa apenas na apresentação, sem atrasar uso. Sem contagem animada de
medição, flash de atualização ou pulsação contínua de alertas. Movimento reduzido
elimina deslocamento decorativo; estados continuam visíveis. Gêmeo segue G-03.

Texto informa objeto, situação e saída possível: “Histórico indisponível. Tentar
consultar novamente.” Evitar “Tudo certo” quando só a conexão foi confirmada.
Valores: vírgula decimal, unidade explícita e precisão do contrato; não inventar
casas adicionais. Horário absoluto com fuso acompanha idade relativa quando útil.
Erros não expõem detalhes internos nem apagam entrada que ainda possa ser corrigida.
