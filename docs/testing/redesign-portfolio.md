# ColdSafe — entrega do redesign para portfólio

## Resultado

A rota `/` apresenta o projeto com tema escuro e mídia simulada; `/dashboard`
contém a operação com tema claro. A nova direção é **tecnologia de precisão**:
tipografia forte, composição organizada e métricas estáveis. Os contratos HTTP,
o polling de 5 segundos e a precedência de estados continuam existentes.

[Figma editável — ColdSafe, Design System e Interfaces](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu)

O acesso da integração foi inicialmente identificado como View, mas a criação
e as edições neste arquivo foram aceitas. Nenhum plano foi contratado.

## O que foi criado, por quê e como

| Arquivo/artefato | Finalidade e implementação |
| --- | --- |
| `frontend/src/views/LandingView.vue` | Apresentação com problema, arquitetura, demonstração e limites. Vue sem chamadas à API; links nativos, Motion por seção e CSS responsivo. |
| `frontend/e2e/landing.spec.ts` | Verifica independência da API, links, teclado, vídeo real, imagens, larguras, redução de movimento e ampliação de 200%. |
| `frontend/e2e/monitoring-api.ts` | Mock HTTP compartilhado pelos testes e pela captura, evitando cenários divergentes. |
| `frontend/scripts/capture-demo.ts` | Grava o frontend com Playwright, usando sete cenas e histórico determinístico. Adiciona faixa de simulação somente ao documento capturado. |
| `frontend/public/media/dashboard-{normal,critical,stale,mobile}.png` | Quatro capturas reais da interface implementada com dados fictícios identificados. |
| `frontend/public/media/coldsafe-demo.webm` | Vídeo de aproximadamente 72 segundos, incluindo normal, período de 24h, atenção, crítico, desatualizado, falha e recuperação do histórico. |
| `frontend/public/media/coldsafe-demo.vtt` | Legendas descritivas em português sincronizadas pela captura. O vídeo não tem narração. |
| `frontend/public/fonts/inter-{latin,latin-ext}.woff2` e `OFL.txt` | Inter variável local, incluindo licença SIL OFL. Evita dependência de requisição externa para tipografia. |
| Este relatório | Registra decisões, mudanças, limitações e como reproduzir a validação. |

## O que foi alterado

| Arquivo | Mudança e motivo |
| --- | --- |
| `frontend/PRODUCT.md` | Registra a nova direção autorizada, público da apresentação, rotas e regras de mídia/movimento. Mantém o histórico da direção anterior. |
| `frontend/src/styles/tokens.css` | Cores semânticas claras/escuras, espaços, tipografia, raios e duração. Um nome descreve uma função, por exemplo `--cs-color-ink-muted`, em vez de uma cor específica. |
| `frontend/src/styles/index.css` | Carregamento local da Inter, números tabulares e regras comuns para mídia. |
| `frontend/src/views/FoundationView.vue` | Nova composição operacional; estado e atualidade próximos, temperatura dominante e histórico amplo. Mensagem de leitura antiga explicita que o estado atual não está confirmado. Cabeçalho do gráfico permite quebra de linha na ampliação. |
| `frontend/src/features/monitoring/TemperatureHistoryChart.vue` | Chart.js lê as cores dos tokens CSS. Mantém resumo textual; animação do gráfico desativada. |
| `frontend/src/features/monitoring/TemperatureHistoryChart.spec.ts` | Verifica a aplicação dos tokens no gráfico. |
| `frontend/src/router/index.ts` | Rotas separadas com importação dinâmica: dashboard não precisa carregar Motion nem mídia da apresentação. |
| `frontend/e2e/dashboard.spec.ts` | Atualiza `/dashboard`, preserva os estados e acrescenta carregamento, recuperação, período e falha parcial. Seletor do ambiente acompanha sua nova linha junto ao dispositivo. |
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

## Verificação executada

Com Node.js **24.20.0**, no diretório `frontend`:

```sh
npm run build
npm run test:coverage
npm run test:e2e
```

- Build e verificação TypeScript: passaram.
- Vitest: **31 testes, 9 arquivos**, todos passaram.
- Cobertura: **87,90% statements, 87,37% branches, 89,39% functions e 89,28% lines**. O limiar global de 80% foi atendido. A landing é exercitada pelos E2E; não tem suíte unitária própria.
- Playwright Chromium: **17 testes**, todos passaram.
- Larguras **320, 375, 768 e 1440 px**: ambas as rotas sem rolagem horizontal.
- Redução de movimento: seções com opacidade 1 e sem transformação; link para pular ao conteúdo acessível pelo teclado e com foco visível.
- Ampliação de **200% via CSS zoom**: conteúdo e controles disponíveis nas duas rotas. É um teste de ampliação/refluxo em Chromium, não uma auditoria de todos os navegadores ou leitores de tela.
- API indisponível na apresentação: nenhuma chamada de monitoramento em mais de dois ciclos de polling simulados.
- Vídeo: duração entre 60 e 90 s, controles nativos, pausado e sem autoplay; imagens carregam e possuem texto alternativo.
- Estados operacionais, recuperação, período e falha parcial verificados com mocks HTTP.
- Contraste calculado dos pares de texto/fundo e estados nos dois temas: todos ≥ 4,5:1; o menor par verificado foi 5,10:1. Isso não equivale a uma certificação WCAG completa.
- Figma: inspeção visual e de limites das telas em 375/768/1440, sem elementos ultrapassando a largura dos frames finais.
- Build gera chunks separados para LandingView e FoundationView.
- `npm install` terminou com auditoria de 175 pacotes e zero vulnerabilidades relatadas no momento da instalação.
- `git diff --check`: passou.
- Revisão independente read-only do código, rotas e captura: nenhum problema concreto encontrado; usou os resultados de build/testes registrados acima.

## Correções encontradas durante a validação

1. **Tipos de terceiros:** conflitos dos `.d.ts` impediram o build. Arquivo: `tsconfig.app.json`. Solução: `skipLibCheck`, mantendo `strict`. Teste: `npm run build`.
2. **Seletor E2E antigo:** procurava o laboratório como texto isolado, mas a composição agora mostra ambiente e dispositivo juntos. Arquivo: `e2e/dashboard.spec.ts`. Solução: selecionar a linha completa. Teste: `npm run test:e2e`.
3. **Ampliação de 200%:** cabeçalho horizontal do histórico não podia quebrar linha. Arquivo: `FoundationView.vue`. Solução: `flex-wrap` e colunas com mínimo zero. O teste de ampliação falhou antes da correção e passou depois.
4. **Auto Layout no Figma:** Fill vertical herdado da composição horizontal comprimia cartões compactos. Solução: altura Hug nas colunas e dimensões explícitas do gráfico; captura final confirmou cartões legíveis.

## Reproduzir a mídia

```sh
# Terminal 1, dentro de frontend/
npm run dev -- --host 127.0.0.1 --port 4175
# Terminal 2, dentro de frontend/
npm run capture:demo
```

A captura precisa do Chromium instalado (`npx playwright install chromium`).
O roteiro reserva 68 segundos de cenas; inicialização/finalização da gravação
acrescentam alguns segundos. O arquivo entregue tem aproximadamente 72 segundos.
Os valores de demonstração são estáticos e identificados como simulados.

## Limites da entrega

Hospedagem, publicação, autenticação, novos cadastros, notificações e controle
de equipamentos continuam fora do escopo. Não houve alteração de backend,
contratos ou firmware. O dashboard operacional precisa da API; somente a
apresentação e sua mídia funcionam sem ela. O registro Git e o resumo da entrega
estão no Notion do projeto. O commit é local, sem push ou publicação do site.
