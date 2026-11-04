# P-04 — Design system ColdSafe

**v0.1 elaborada em 27/10/2026 e aprovada para o planejamento em 28/10/2026.
Implementação não iniciada.**

Direção confirmada: **Precisão operacional**. Aplicação clara, Inter local e
acento petróleo; a apresentação pública conserva o tema escuro existente.
O sistema deve ajudar a identificar objeto, estado, atualidade e próxima ação.

## Usar e retomar

| Preciso definir… | Referência mínima |
| --- | --- |
| Cor, tipo, espaço, forma, movimento e critérios de acesso | [Fundamentos](foundations.md) |
| Navegação, ações, formulários, dados e padrões de página | [Componentes e padrões](components.md) |
| Cena, seleção, rótulos e inspeção do equipamento | [Gêmeo digital](digital-twin.md) |
| Aparência dos exemplos | [Prancha 01](../assets/design-system-01.png), [prancha 02](../assets/design-system-02.png) ou [PDF](../assets/design-system.pdf) |
| Destinos, contexto e regras de acesso | [Mapa P-02](../information-architecture.md) e [ajustes P-03](../path-evaluation.md) |

Fontes visuais editáveis: [SVG da prancha 01](../assets/design-system-01.svg) e
[SVG da prancha 02](../assets/design-system-02.svg). Incorporam a fonte Inter local;
a segunda incorpora a referência já aprovada. PNGs e PDF foram renderizados desses
SVGs, sem instalar dependências ou iniciar o ColdSafe. Os exemplos visuais não
possuem interações; os equivalentes textuais estão nos documentos desta pasta.

Para uma tarefa futura, ler este guia e somente a seção pertinente. Os IDs F, C e
G identificam regras, não cartões de implementação. Os cartões da P-06 deverão
apontar para esses IDs, fontes atuais e critérios de teste.

## Autoridade e estado das decisões

- **Confirmado pelo usuário:** direção visual, imagem conceitual e mapa da P-03.
- **Existente, conferido em código:** tokens, fonte, estilos globais e componentes
  de domínio citados nos documentos. Existir não significa estar validado nesta rodada.
- **Proposto nesta P-04:** aplicações dos tokens, medidas de composição, catálogo
  de padrões, textos e acabamento do gêmeo. Aprovados como referência de
  planejamento em 28/10/2026; aplicação e verificação funcional continuam futuras.
- **Exemplo estático:** pranchas; valores e gráficos fictícios, sem conexão com API.
  A miniatura do gêmeo reproduz a imagem aprovada sem alterar seu arquivo original.

Em conflito, contratos/código determinam dados e permissões; mapa confirmado
determina destinos. Este sistema orienta a aparência futura. A imagem anterior
não prevalece sobre os nomes da P-03, o histórico atual de 15 min do gêmeo ou
funções ausentes. Não existe um design system completo implementado por esta entrega.

## O que já pode ser reaproveitado

[tokens.css](../../../frontend/src/styles/tokens.css) e
[index.css](../../../frontend/src/styles/index.css) centralizam os fundamentos.
O histórico, previsão, LED, estado do LLM e alvo de treinamento já possuem
componentes de domínio reutilizados; ver fontes na [matriz C-00](components.md#c-00--base-existente).
Botões, campos, painéis e menus ainda usam muita marcação/estilo local.

Na implementação futura, consolidar padrões com o mesmo propósito e repetição
comprovada; não criar uma biblioteca inteira antes de migrar os primeiros usos.
Preservar lógica e testes dos componentes de domínio. Um painel de previsão e
um formulário não devem ganhar a mesma organização apenas por terem bordas.

Não há biblioteca, ícones, fonte, motor 3D ou dependência nova escolhida nesta P-04.
Usar ícones atuais/nativos ou desenhos simples já presentes, sempre com rótulo nas
ações importantes. Uma família adicional exigirá necessidade e licença verificadas.

## Evidências, verificação e limites

- Leitura dos tokens/estilos, produto, inventário e componentes selecionados;
  revisão independente localizou reutilizações e diferenças entre páginas.
- Cálculo de contraste sRGB para 20 pares dos temas claro/escuro, documentado em
  F-02; números arredondados só para apresentação, aprovação pelo valor integral.
- Pranchas conferidas visualmente e documentação conferida por links, âncoras,
  valores de tokens e correspondência das dez rotas. Relato final na seção abaixo.
- Sem execução do ColdSafe, testes funcionais, leitor de tela, estudo com pessoas,
  calibração física ou medição de desempenho 3D. Acessibilidade não está certificada.

### Fechamento desta versão

Especificação e pranchas entregues para revisão em 27/10/2026:

- Criados quatro documentos, duas pranchas em SVG/PNG e PDF com duas páginas;
  atualizados índice, plano e registro de fontes do redesign.
- Conferidos 130 links/âncoras locais nos dez documentos do redesign, 19 papéis de
  cor nos dois temas contra os tokens atuais, 20 pares de contraste e dez rotas
  na matriz de famílias. Formatação conferida, inclusive dos arquivos novos.
- Pranchas inspecionadas em 1440 × 1760 px, fonte Inter carregada e nenhum texto
  além dos limites externos. Ajustado afastamento da unidade no eixo do gráfico
  e confirmado sem sobreposição. Isso verifica a prancha, não o layout responsivo.
- SVGs válidos; PNGs nas dimensões previstas; PDF com duas páginas e texto extraível.
- Revisão independente incorporou regras de foco/modal e anúncios do Assistente.
  Nenhuma dependência adicionada ou arquivo do aplicativo alterado nesta etapa.

A fonte completa de contexto e aparência é esta proposta e seus exemplos;
renderização estática não demonstra interações. Em 28/10/2026, o usuário aprovou
esta versão (“próxima, essa ficou boa”) e escolheu avançar para a P-05.

**Retomada atual:** P-05 aprovada e [P-06 documentada](../tasks/README.md).
Aguardar escolha do usuário para iniciar um cartão de implementação.
