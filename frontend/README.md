# Frontend ColdSafe

Apresentação de portfólio em `/` e dashboard operacional em `/dashboard`,
com a direção **tecnologia de precisão**. A apresentação funciona sem backend.
No dashboard, cadastro/login, ambientes, dispositivos e limites usam REST
autenticado. A leitura atual, os alertas e o estado do LED acompanham o
dispositivo selecionado. Eventos WebSocket atualizam a tela; após reconexão,
REST recupera o estado atual e o histórico.

Na B2-14, `VITE_AIOT_ENABLED=true` seleciona explicitamente HTTP/WS v3. O
dashboard mostra as seis medições, equipamento e estados observados dos atuadores;
o seletor de grandeza reutiliza gráfico, tooltip e tabela. Zero é valor válido;
ausência de sensor em histórico legado é indisponibilidade. Estado observado
na telemetria e confirmação de comando são informações separadas. Só ACK válido
confirma o pedido; timeout/rejeição permanecem explícitos. Nenhuma biblioteca nova.

No Compose, use `compose.aiot.yaml`: ele habilita o backend e passa o argumento
de build do frontend. É necessário reconstruir `frontend` ao alterar esse modo.
No Vite local, defina a variável antes de iniciar o processo e configure
`VITE_API_BASE_URL` para o backend v3. Sem a flag, preserva-se o fluxo v1/v2;
falhas/403/404 não causam fallback silencioso entre versões. Login e catálogo
continuam nas rotas v1 em ambos os modos.

- [Definição do produto](PRODUCT.md).
- [Figma editável](https://www.figma.com/design/EIn6llJ5Fc3uIFlIDdokZu).
- [Relatório: arquivos, decisões, mídia e validação](../docs/testing/redesign-portfolio.md).

A direção anterior, Caderno de bancada, foi aprovada na CS-26 em 09/09/2026.
O redesign atual foi autorizado no plano de portfólio e mantém suas regras
operacionais: atualidade explícita, estados com texto e falhas parciais.

## Como executar

No Compose normal, a B2-08 serve o build estático com Nginx sem root na porta
`5173`; REST, `/docs`, `/openapi.json` e WebSocket passam pelo mesmo endereço.
Não há Vite, npm ou fontes montados no container final. O build usa base REST
relativa e resolve WebSocket pela origem da página. `compose.debug.yaml` habilita
portas locais de diagnóstico e um link RabbitMQ no dashboard; `/docs` tem link
permanente. Preparação e segredos estão no [runbook](../docs/runbook.md).
As instruções a seguir são para o desenvolvimento local com Vite.

- Referência de runtime: Node.js `24.20.0`.
- Instalar dependências fixadas: `npm ci`.
- Iniciar o ambiente local: `npm run dev`.
- Validar tipos e gerar a build: `npm run build`.
- Executar os testes unitários do frontend: `npm run test:unit:run`.
- Instalar o Chromium usado pelos testes E2E: `npx playwright install chromium`.
- Executar os cenários E2E das duas interfaces: `npm run test:e2e`.

Os testes E2E sobem o Vite automaticamente e simulam as fronteiras HTTP e
WebSocket da API. Assim, estados normais, alertas, reconexão e falhas são
reproduzíveis sem depender do InfluxDB ou do MQTT.

A suíte real opt-in `backend/tests/infra/test_dashboard_integration.py` sobe
brokers/bancos/gateway/writer/simulador descartáveis, backend Uvicorn e Vite
locais, e executa `e2e/aiot-real.spec.ts`. Não usa mocks de HTTP/WS. Requer Docker,
Python/lock dev, Node 24.20.0, dependências frontend e Chromium instalados:

```sh
COLDSAFE_WRITER_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_dashboard_integration.py -q --no-cov -o addopts=''
```

Execute da raiz do projeto. `COLDSAFE_NODE_BINARY` pode indicar o executável Node;
`COLDSAFE_FRONTEND_NODE_MODULES`, uma instalação temporária feita com o mesmo lock.
O teste copia fontes/configuração e usa credenciais/volumes próprios, removidos
ao terminar. Fora do harness, os quatro casos reais ficam explicitamente pulados.

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
um WebM de cerca de 81 segundos e legendas VTT em `public/media/`.
Não precisa de backend. A faixa “DEMONSTRAÇÃO SIMULADA” existe somente na
captura. O vídeo também explica por texto cada cenário, incluindo a confirmação
simulada de um comando. Para conferir arquivos antes de substituir a mídia,
defina `CAPTURE_OUTPUT_DIR` com uma pasta temporária.

## Motion e tipagem

Foram adicionados `motion-v@2.4.2` e `@vueuse/core@14.4.0`, fixados no lock.
O Motion fica no chunk da apresentação. `skipLibCheck` evita conflitos nas
declarações de terceiros (tipos HTML/VueUse/React/Bluetooth); `strict` e
a checagem dos arquivos da aplicação continuam ativos. Reavaliar essa opção
quando as declarações dessas dependências forem compatíveis entre si.
Inter é servido localmente, com licença OFL em `public/fonts/OFL.txt`.
