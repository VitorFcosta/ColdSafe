# ColdSafe — entrega do redesign para portfólio

## Resultado

A rota `/` apresenta o projeto com tema escuro e mídia simulada; `/dashboard`
contém a operação com tema claro. A direção é **tecnologia de precisão**:
tipografia forte, composição organizada e métricas estáveis. Eventos chegam por
WebSocket; REST carrega o estado inicial e o recupera ao reconectar.

[Figma editável — ColdSafe, Design System e Interfaces](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu)

O acesso da integração foi inicialmente identificado como View, mas a criação
e as edições neste arquivo foram aceitas. Nenhum plano foi contratado.

## O que foi criado, por quê e como

| Arquivo/artefato | Finalidade e implementação |
| --- | --- |
| `frontend/src/views/LandingView.vue` | Apresentação com problema, arquitetura, demonstração e limites. Vue sem chamadas à API; links nativos, Motion por seção e CSS responsivo. |
| `frontend/e2e/landing.spec.ts` | Verifica independência da API, links, teclado, vídeo real, imagens, larguras, redução de movimento e ampliação de 200%. |
| `frontend/e2e/monitoring-api.ts` | Mock HTTP compartilhado pelos testes e pela captura, evitando cenários divergentes. |
| `frontend/scripts/capture-demo.ts` | Grava o frontend com Playwright, usando oito cenas e histórico determinístico. Adiciona faixa de simulação somente ao documento capturado. |
| `frontend/public/media/dashboard-{normal,critical,stale,mobile}.png` | Quatro capturas reais da interface implementada com dados fictícios identificados. |
| `frontend/public/media/coldsafe-demo.webm` | Vídeo de 81,44 segundos, incluindo normal, período de 24h, atenção, crítico, desatualizado, falha e recuperação do histórico e comando LED pendente/confirmado. |
| `frontend/public/media/coldsafe-demo.vtt` | Legendas descritivas em português sincronizadas pela captura. O vídeo não tem narração. |
| `frontend/public/fonts/inter-{latin,latin-ext}.woff2` e `OFL.txt` | Inter variável local, incluindo licença SIL OFL. Evita dependência de requisição externa para tipografia. |
| Este relatório | Registra decisões, mudanças, limitações e como reproduzir a validação. |

## O que foi alterado

| Arquivo | Mudança e motivo |
| --- | --- |
| `frontend/PRODUCT.md` | Registra a nova direção autorizada, público da apresentação, rotas e regras de mídia/movimento. Mantém o histórico da direção anterior. |
| `frontend/src/styles/tokens.css` | Cores semânticas claras/escuras, espaços, tipografia, raios e duração. Um nome descreve uma função, por exemplo `--cs-color-ink-muted`, em vez de uma cor específica. |
| `frontend/src/styles/index.css` | Carregamento local da Inter, números tabulares e regras comuns para mídia. |
| `frontend/src/views/FoundationView.vue` | Composição operacional; estado e atualidade próximos, temperatura dominante e histórico amplo. Mensagem de leitura antiga explicita que o estado atual não está confirmado. Navegação e medições se reorganizam em texto ampliado. |
| `frontend/src/features/monitoring/TemperatureHistoryChart.vue` | Chart.js lê as cores dos tokens CSS. Mantém resumo textual; animação do gráfico desativada. |
| `frontend/src/features/monitoring/TemperatureHistoryChart.spec.ts` | Verifica a aplicação dos tokens no gráfico. |
| `frontend/src/router/index.ts` | Rotas separadas com importação dinâmica: dashboard não precisa carregar Motion nem mídia da apresentação. |
| `frontend/e2e/dashboard.spec.ts` | Preserva estados, carregamento, recuperação, período, comandos e falha parcial. `dashboard-selection.spec.ts` verifica seleção, recarga e troca de conta. |
| `frontend/package.json` e `package-lock.json` | Dependências fixadas e comando `capture:demo`. |
| `frontend/tsconfig.app.json` | `skipLibCheck: true` para conflitos nas declarações das bibliotecas; `strict` e a checagem da aplicação continuam ativos. |
| `frontend/README.md`, `README.md`, `docs/runbook.md`, `docs/version-matrix.md` | Rotas, execução, mídia, compatibilidade e versões instaladas. No README principal, foram preservadas as alterações que já existiam antes desta entrega. |

## Ferramentas e dependências

- **Adicionadas:** `motion-v@2.4.2` e `@vueuse/core@14.4.0`, versões exatas no manifesto e lock.
- **Motion for Vue:** entradas únicas das seções e sequência das etapas. Sem contadores numéricos ou movimento contínuo. Redução de movimento torna o conteúdo imediatamente visível. [Documentação oficial](https://motion.dev/docs/vue).
- **21st.dev:** referência de organização de blocos e sequência visual; a implementação Vue é própria. Nenhum trecho React ou componente de terceiros foi copiado, portanto nenhuma licença de código desses exemplos foi incorporada. Referências: [bento](https://docs.21st.dev/blog/react-bento-grid-components), [timeline](https://docs.21st.dev/blog/react-timeline-components) e [feature sections](https://docs.21st.dev/blog/react-feature-section-components).
- **UI/UX Pro Max:** dispensado conforme o plano; não instalado.
- **Inter:** arquivos distribuídos pelo Google Fonts, licença incluída em `public/fonts/OFL.txt`.

As declarações de `motion-v` e suas dependências apresentam conflitos de tipos
Vue/HTML, VueUse, React e Bluetooth nesta combinação de versões. `skipLibCheck`
ignora a checagem interna dos arquivos `.d.ts` de terceiros, sem desativar a
verificação dos arquivos da aplicação. É uma limitação conhecida a reavaliar
numa atualização compatível dessas bibliotecas. Build e testes de navegador
confirmam a integração executável, não a consistência interna desses `.d.ts`.

## Figma e correspondência com o código

O arquivo contém oito páginas: orientações, fundamentos, ações, monitoramento,
componentes de apresentação, apresentação, dashboard e especificações.
Fundamentos usam variáveis, modos claro/escuro, estilos de texto e Auto Layout.
Componentes incluem Button, StatusBanner, MetricCard, PeriodSelector,
HistoryPanel, ArchitectureStep e MediaFrame. Há variantes apenas para os estados
utilizados. Nomes `color/*`, `space/*` e `type/*` correspondem aos tokens CSS.

- [Apresentação desktop](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=14-2), [375 px](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=19-21), [768 px](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=19-109).
- [Dashboard desktop](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=13-2), [375 px](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=17-48), [768 px](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=17-105).
- [Especificações e mapa Vue](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu?node-id=23-2).

A página Dashboard também contém telas de atenção, crítico, desatualizado,
sem dados, erro de serviço, carregamento e falha parcial do histórico. O gráfico
no Figma é ilustrativo; o gráfico executável usa Chart.js e respostas validadas.
Nos layouts compactos, algumas instâncias foram expandidas em frames editáveis
para corrigir relações Fill/Hug; os tokens continuam vinculados.

Botões da apresentação conectam a seção de demonstração e o repositório;
variantes do seletor de período têm interações entre si. A mídia no Figma usa
pôster estático com as capturas reais. Reprodução e legendas são funções do
vídeo nativo no navegador, não uma simulação de player dentro do Figma.

## Validação final UX-17 — 27/09/2026

Executada localmente com Node.js **22.19.0**; o runtime documentado do projeto é
24.20.0. No diretório `frontend`, `npm run build` passou, incluindo checagem de
tipos. `npm run test:coverage` passou: **89/89 testes em 16 arquivos**; cobertura
global **89,33% de statements, 83,41% de branches, 89,30% de functions e
92,94% de lines**. `npm run test:e2e` passou **30/30 cenários Chromium** na
rodada final. `git diff --check` passou. A build tem **7,3 MB** no total,
incluindo o vídeo de **6.426.882 bytes**; LandingView e FoundationView continuam
em chunks separados.

- E2E cobre landing sem API, login/logout, navegação por teclado, seleção e troca
  de conta, gestão e limites, quatro períodos, tabela, alertas, estados normal,
  atenção, crítico, antigo, vazio, carregamento, erro, reconexão e comando LED.
  Fronteiras REST/WebSocket são simuladas: isso verifica o frontend, não o
  hardware ou a operação integrada com banco/MQTT.
- Em Chromium, rotas `/` e `/dashboard` não criaram rolagem horizontal em
  **320, 375, 768 e 1440 px**. As quatro rotas foram verificadas em **360 px**
  com texto raiz ampliado para 200%, sem rolagem horizontal após correções.
  O teste anterior de CSS `zoom: 2` passou; CSS zoom não equivale a zoom de
  navegador. O refluxo a 360 px é uma aproximação do zoom 400% em janela de
  1440 px, sem certificar todos os navegadores.
- Teclado/foco, redução de movimento, textos alternativos, labels, estados e
  resumos de gráficos foram conferidos pelos testes e pelo navegador. Os pares
  principais de texto/fundo medidos ficaram entre **5,10:1 e 16,06:1**;
  borda funcional no branco, **4,31:1**. Não foi feita sessão manual completa
  com VoiceOver/NVDA; nenhuma conformidade WCAG integral é reivindicada.
- A landing fez **zero** chamadas de monitoramento. Uma abertura do dashboard
  com mocks em 1,2 s fez um WebSocket, duas leituras de resumo, duas de atuadores,
  quatro de histórico (incluindo comparação), uma de alertas e duas de catálogo.
  O segundo resumo ocorre na abertura do WebSocket para sincronização; não houve
  ciclo contínuo de requisições no intervalo observado. Isto não mede carga real
  da API sob operação prolongada.
- Quatro PNGs e quadros do vídeo foram abertos; reprodução em desktop e celular
  avançou até 75 s com oito legendas ativas. O vídeo tem controles nativos,
  poster e não inicia sozinho. A aparência das legendas depende do navegador.

## Correções encontradas durante a validação

1. **Tipos de terceiros:** conflitos dos `.d.ts` impediram o build. Arquivo: `tsconfig.app.json`. Solução: `skipLibCheck`, mantendo `strict`. Teste: `npm run build`.
2. **Seletor E2E antigo:** procurava o laboratório como texto isolado, mas a composição agora mostra ambiente e dispositivo juntos. Arquivo: `e2e/dashboard.spec.ts`. Solução: selecionar a linha completa. Teste: `npm run test:e2e`.
3. **Ampliação de 200%:** cabeçalho horizontal do histórico não podia quebrar linha. Arquivo: `FoundationView.vue`. Solução: `flex-wrap` e colunas com mínimo zero. O teste de ampliação falhou antes da correção e passou depois.
4. **Auto Layout no Figma:** Fill vertical herdado da composição horizontal comprimia cartões compactos. Solução: altura Hug nas colunas e dimensões explícitas do gráfico; captura final confirmou cartões legíveis.
5. **Texto ampliado:** `body { min-width: 20rem }` dobrava a largura mínima com texto em 200%, e navegação/cartões não quebravam corretamente. Arquivos: `src/styles/index.css`, `LandingView.vue`, `FoundationView.vue`, `ManageView.vue` e `AlertsComparisonPanel.vue`. Solução: mínimo fixo de 320 px e quebra de linha/coluna nos pontos estreitos. Teste E2E novo falhou com 640 px de largura em uma janela de 360 px e depois passou nas quatro rotas.
6. **Espera de navegação no E2E:** uma rodada completa falhou de forma intermitente ao chamar voltar antes da confirmação da rota. Arquivo: `e2e/dashboard-selection.spec.ts`. Solução: esperar `/manage` e `/dashboard` após os cliques. Teste focado passou; a rodada completa final está registrada acima.

## Reproduzir a mídia

```sh
# Terminal 1, dentro de frontend/
npm run dev -- --host 127.0.0.1 --port 4175
# Terminal 2, dentro de frontend/
npm run capture:demo
```

A captura precisa do Chromium instalado (`npx playwright install chromium`).
O roteiro reserva 80 segundos para oito cenas; inicialização/finalização da
gravação acrescentam pouco mais de um segundo. O arquivo entregue tem 81,44
segundos. Os valores e a confirmação do LED são simulados e identificados.

## Limites da entrega

Hospedagem, publicação, notificações externas e controle real de equipamentos
continuam fora do escopo. Autenticação e cadastros existem no frontend; a
integração real com duas contas, banco, MQTT e hardware não foi reexecutada nesta
validação. Não houve alteração de backend, contratos ou firmware. O dashboard
operacional precisa da API; somente a apresentação e sua mídia funcionam sem
ela. As mudanças desta frente estão sem commit, push, merge ou publicação.
