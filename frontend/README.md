# Frontend

Esta área contém o dashboard Vue 3 com a direção **Caderno de bancada** e a
composição **B — Gráfico ampliado**, aprovadas em 09/09/2026 na CS-26.

O dashboard implementa o diagnóstico atual, o gráfico de temperatura, os
períodos de consulta, o polling e as falhas parciais. A fundação técnica, os
tokens visuais e o mapeamento dos estados da interface possuem testes
automatizados.

A definição confirmada do produto, do público, do escopo e das restrições está
em [`PRODUCT.md`](PRODUCT.md).

Desktop, mobile e os oito estados da interface foram aprovados. O registro das
decisões e as imagens estão na [CS-26 no Notion](https://app.notion.com/3cfd67001da981108554cd452d3191b7).
Os arquivos locais de trabalho do Impeccable ficam em `.impeccable/`, fora do Git.

A composição mantém estado e atualidade juntos, temperatura dominante e histórico
amplo abaixo das métricas. No mobile, as informações são empilhadas. Falha do
histórico preserva a leitura atual válida; leitura antiga aparece como última
leitura conhecida, sem confirmar o estado atual.

## Como executar

- Referência de runtime: Node.js `24.20.0`.
- Instalar dependências: `npm install`.
- Iniciar o ambiente local: `npm run dev`.
- Validar tipos e gerar a build: `npm run build`.
- Executar os testes unitários do frontend: `npm run test:unit:run`.
- Instalar o Chromium usado pelos testes E2E: `npx playwright install chromium`.
- Executar os seis cenários E2E do dashboard: `npm run test:e2e`.

Os testes E2E sobem o Vite automaticamente e simulam somente a fronteira HTTP
da API. Assim, os estados normal, atenção, crítico, leitura desatualizada, sem
dados e erro de serviço são reproduzíveis sem depender do InfluxDB ou do MQTT.

### Compatibilidade de versões

O planejamento inicial fixava TypeScript `7.0.2`. Nesta fundação ele foi fixado
em `6.0.3`: o `vue-tsc` `3.3.11` falha com o TypeScript 7 porque a versão 7 não
exporta mais o caminho interno que o verificador Vue utiliza. Essa é a menor
troca que preserva a verificação de tipos; a versão deve ser reavaliada quando
o `vue-tsc` oferecer suporte explícito ao TypeScript 7.

Os tokens vivem em `src/styles/tokens.css`. Eles definem papéis semânticos — por
exemplo, tela, superfície, texto, foco e estados normal, atenção, crítico e
desatualizado — em vez de amarrar cores a componentes específicos. Isso permite
que desktop e mobile conservem os mesmos significados visuais.

Contraste, navegação por teclado e responsividade foram validados no dashboard
implementado; os mockups foram usados apenas como direção visual.
