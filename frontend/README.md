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

A B2-15 acrescenta `/messaging`, acessível pela navegação como **Mensageria**.
O painel administrativo mostra as dez filas atuais, contagens, taxas por segundo e
consumidores; consulta apenas a API ColdSafe com a sessão existente, nunca o
RabbitMQ diretamente. Atualiza a cada cinco segundos e informa a idade da coleta.
Falha conserva o último snapshot somente com aviso explícito; taxa ausente não
vira zero. As métricas são agregadas da infraestrutura e restritas a admin.
Não há acesso a corpos de mensagens ou credenciais do broker.
Para habilitar apenas essa página, use `compose.messaging.yaml` junto do Compose
base e reconstrua backend/frontend. Esse overlay conserva o modo do dashboard;
não exige a ativação do percurso AIoT completo. Procedimento em
[configuração de Mensageria](../docs/configuration.md#mensageria-b2-15).

A B2-16 mostra também últimas mensagens e cópias da DLQ, por resumos privados
de até 100 itens por lista. Somente mensagens de dispositivos/ambientes atualmente
pertencentes ao admin entram na resposta; corpos brutos e credenciais não chegam
ao navegador. A tela informa conexão/atualidade do observador e falha de consulta.
O controle de parada/retomada do gravador continua no terminal, conforme
[runbook](../docs/runbook.md#mensageria-b2-16-parar-e-retomar-o-gravador).

A B2-19 acrescenta `/laboratory`, acessível como **Laboratório** na navegação.
Admin configura todos os parâmetros do gerador, confere a estimativa antes de
enfileirar e acompanha o estado durável por HTTP autenticado. O ID fica em
`?job=UUID` para recarregar/retomar sem repetir o POST. O resumo mostra configuração,
seed, autor, contagem e qualidade observada; a amostra de dez linhas é solicitada
separadamente. Dados sintéticos e labels não entram no monitoramento live.
As limitações da simulação, censura de RUL e taxa configurada de outliers ficam
explícitas na página. O backend precisa do [overlay de jobs](../docs/configuration.md#jobs-assíncronos-b2-17)
e da montagem de artefatos RO; reconstruir o frontend disponibiliza a rota.

Teste Web real, da raiz e com PostgreSQL descartável configurado por
`POSTGRES_TEST_HOST/PORT/DB/USER/PASSWORD`, Docker e Chromium instalados:

```sh
COLDSAFE_LAB_INTEGRATION=1 COLDSAFE_RABBITMQ_INTEGRATION=1 python -m pytest backend/tests/integration/test_laboratory_integration.py -q -s --no-cov -o addopts=''
```

O harness cria/remove um banco isolado, um broker e arquivos temporários próprios;
não o aponte para credenciais pessoais. Usa Node 24/dependências do lock e aceita
`COLDSAFE_NODE_BINARY`/`COLDSAFE_FRONTEND_NODE_MODULES`. Exercita geração real de
um milhão, recarga sem reenvio, resumo/amostra privados, teto e falha após um
bloco durável. Login HTTP é real; a sessão obtida é colocada no navegador pelo
harness para limitar o teste ao Laboratório. Não simula respostas HTTP/AMQP.

A B2-23 acrescenta `/training` (**Treinamento**), com seleção de dataset próprio
concluído e link direto a partir do Laboratório. Admin envia um job real,
acompanha duas etapas e recupera o estado por `?job=UUID` sem repetir o POST.
Saúde e RUL mostram MAE/RMSE/R², baseline, gate de validação, previsto × real,
tabela de erros e importância por permutação com sinal. Métricas completas e
amostra reservada são identificadas separadamente. Versões, seeds, split e
limitações sintéticas/censura ficam visíveis; nenhum resultado ativa o pacote.
Falha de consulta permite repetir GET; envio incerto não é repetido automaticamente.

Reutiliza Vue/Chart.js e sessão existente, sem dependências novas. A página segue
o acesso administrativo do Laboratório; o backend protege POST por papel atual
e GET por dono. Requer worker `training` e montagem RO dos resultados na API,
conforme [configuração de jobs](../docs/configuration.md#jobs-assíncronos-b2-17).
Teste simulado específico: `npm run test:e2e -- training.spec.ts`.
Teste real completo pelo [harness B2-23](../backend/README.md#treinamento-integrado-e-resultados-b2-23),
que também confere os valores contra relatórios e captura desktop/mobile.

A B2-25 acrescenta **Previsão do equipamento** no dashboard AIoT: saúde em pontos
0–100, RUL em horas (zero é válido), versão do pacote/features e horários da entrada
e cálculo. Falta de modelo/histórico, features inválidas, modelo indisponível e
leitura vencida têm mensagens distintas. Resultado só aparece se vinculado à
leitura atual; não reaproveita previsão anterior quando chega outra telemetria.
WS dispara recuperação REST e a idade local oculta valores vencidos. A troca de
versão aparece sem recarga da página; ativação continua na API administrativa.

Sem dependência nova. `PredictionPanel.vue` reutiliza tokens e texto semântico;
o modo legado conserva seu contrato. Teste simulado: `npm run test:e2e -- inference.spec.ts`.
O [harness real](../backend/README.md#inferência-ao-vivo-b2-25) verifica worker,
RabbitMQ, PostgreSQL, HTTP/WS e Chromium, com fixtures explícitas na fonte/recibo.
Janelas de produção continuam 15 min/1 h; o warm-up pode exigir uma hora de coleta.
Configuração do worker está no [guia](../docs/configuration.md#inferência-ao-vivo-b2-25).

Para o dashboard v3 no Compose, use `compose.aiot.yaml`: ele habilita o backend e passa o argumento
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

A B2-15 tem um harness separado, que compara contagens/taxas/consumidores com
RabbitMQ real, verifica permissões e pausa o broker para exercitar timeout e
recuperação; também executa os quatro cenários Chromium de Mensageria:

```sh
COLDSAFE_WRITER_INTEGRATION=1 .venv/bin/python -m pytest backend/tests/infra/test_messaging_integration.py -q -s --no-cov -o addopts=''
```

Requer os mesmos runtimes/dependências e aceita `COLDSAFE_NODE_BINARY` e
`COLDSAFE_FRONTEND_NODE_MODULES`. Use somente via harness: ele cria contas admin,
operator e viewer temporárias, sem alterar usuários/credenciais da pilha pessoal.
O spec `messaging-real.spec.ts` fica pulado sem as variáveis privadas do harness.

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
