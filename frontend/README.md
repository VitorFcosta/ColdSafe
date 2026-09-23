# Frontend ColdSafe

Apresentação de portfólio em `/` e dashboard operacional em `/dashboard`,
com a direção **tecnologia de precisão**. A apresentação funciona sem backend.
O dashboard mantém os contratos HTTP, os períodos de histórico e o polling
a cada 5 segundos.

- [Definição do produto](PRODUCT.md).
- [Figma editável](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu).
- [Relatório: arquivos, decisões, mídia e validação](../docs/testing/redesign-portfolio.md).

A direção anterior, Caderno de bancada, foi aprovada na CS-26 em 09/09/2026.
O redesign atual foi autorizado no plano de portfólio e mantém suas regras
operacionais: atualidade explícita, estados com texto e falhas parciais.

## Como executar

- Referência de runtime: Node.js `24.20.0`.
- Instalar dependências: `npm install`.
- Iniciar o ambiente local: `npm run dev`.
- Validar tipos e gerar a build: `npm run build`.
- Executar os testes unitários do frontend: `npm run test:unit:run`.
- Instalar o Chromium usado pelos testes E2E: `npx playwright install chromium`.
- Executar os cenários E2E das duas interfaces: `npm run test:e2e`.

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

## Demonstração reproduzível

Com Node 24.20.0, execute em dois terminais:

```sh
npm run dev -- --host 127.0.0.1 --port 4175
```

```sh
npm run capture:demo
```

O script usa Playwright e os mesmos mocks HTTP dos E2E. Gera quatro PNGs,
um WebM de cerca de 72 segundos e legendas VTT em `public/media/`.
Não precisa de backend. A faixa “DEMONSTRAÇÃO SIMULADA” existe somente na
captura. O vídeo também explica por texto cada cenário.

## Motion e tipagem

Foram adicionados `motion-v@2.4.2` e `@vueuse/core@14.4.0`, fixados no lock.
O Motion fica no chunk da apresentação. `skipLibCheck` evita conflitos nas
declarações de terceiros (tipos HTML/VueUse/React/Bluetooth); `strict` e
a checagem dos arquivos da aplicação continuam ativos. Reavaliar essa opção
quando as declarações dessas dependências forem compatíveis entre si.
Inter é servido localmente, com licença OFL em `public/fonts/OFL.txt`.
