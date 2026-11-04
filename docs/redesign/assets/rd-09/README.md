# RD-09 — Evidências da integração 3D

Checkpoint final em 31/10/2026. Medições gravadas em UTC nos JSONs; os ensaios
ocorreram na noite de 30/10 no fuso America/Sao_Paulo. Base Git `27bba6f`, com
alterações locais anteriores preservadas. Nenhum commit ou dependência nova.

## O que cada evidência comprova

- [benchmark.json](benchmark.json): build otimizado do comparador, importando a
  **mesma cena de produção**, fixtures controladas, sem API/atuadores. MacBookPro17,1,
  Apple M1, 8 GB, macOS 27.0.1, Chromium 153.0.8010.12, viewport 1440×1000,
  DPR 2, aquecimento de 3 s e janela de pelo menos 60 s por cena. GPU reportada
  como ANGLE Metal Apple M1; não é software renderer.
- Candidata integrada: 59,9901 FPS, p95 17,5 ms, 23.334 triângulos, 55 calls
  incluindo passes de sombra; nove seleções entre 4,6 e 43 ms. Todos dentro dos
  limites originais; nada foi arredondado para aprovar um limiar.
- Inatividade: zero renders no intervalo de 1 s após pausa, stale, equipamento
  parado e movimento reduzido. Dez montagens com 45 geometrias, 3 texturas e
  5 programas estáveis (incluindo seleção); zero contextos vivos após cada desmontagem, sem truncar
  rastreamento. Isso não é medição irrestrita do heap/VRAM do processo inteiro.
- O campo `passedDesktopCriteria` do benchmark continua **false**: nesse navegador
  automatizado a tentativa de outra aba/minimização não produziu `document.hidden`.
  Não houve simulação desse sinal para declarar a medição real aprovada.
- [visibility-native.json](visibility-native.json): ensaio complementar com o
  mesmo build, Chromium instalado iniciado diretamente, perfil temporário e CDP
  sem emulação de foco. Outra aba produziu `document.hidden=true`; contador de
  renders e rotor ficaram estáveis por mais de 1,5 s. A volta ativou novamente o
  loop. [verification.json](verification.json) combina explicitamente essas fontes,
  sem modificar o relatório original. Não implica que desabilitar foco em uma
  sessão CDP separada resolva o comportamento do Playwright — essa tentativa não
  foi suficiente no diagnóstico.
- [coverage.log](coverage.log): 690 testes/53 arquivos; statements 94,82%, branches
  91,06%, functions 92,39%, lines 97,6%. Escopo/exclusões da configuração mantidos.
- [build.log](build.log): tipagem/build finais aprovados; chunk do gêmeo 596,83 kB,
  gzip 154,21 kB, com a legenda corrigida. Aviso acima de 500 kB mantido, sem aumentar o limite configurado.
- [e2e.log](e2e.log): 12 E2E, um worker, HTTP/WS simulados e canvas WebGL real;
  nove IDs, pausa, dados durante pausa, foco, seleção, stale/redução, fallback e
  regressões de LED/ACK/viewer. Não comprova integração com backend ou hardware IoT.

## Imagens e revisão

`desktop.png`/`mobile.png` e as variantes `*-viewport.png` mostram a página com o
LED selecionado e animação pausada. `scene-desktop.png`/`scene-mobile.png` mostram
o enquadramento do canvas; não são imagens usadas para substituir a cena.
`pause-320-text-200.png`/`reflow.json` registram foco no controle, texto de 32 px e
largura/scrollWidth de 320 px. Mobile é viewport/toque emulado, sem medição nova
de GPU física móvel. O teste móvel relatado pelo usuário pertence ao aceite RD-02.

Revisão visual independente por `a11y-architect`, substituindo o perfil específico
de finish Impeccable indisponível: **SHIP no recorte RD-09**, sem achado material.
Conferiu candidata aprovada, câmera, volumes, seleção, controle e reflow; a revisão
não executou testes nem converteu capturas em evidência funcional. Nenhum teste de
leitor de tela ou estudo com participantes nesta entrega.

[detector.json](detector.json): única execução mecânica, um warning `side-tab`
na borda de alerta já existente em DigitalTwinView.vue:160, idêntica ao backup
anterior à tarefa. Não pertence à nova cena/controle; composição da página é RD-10.
Não houve alteração para silenciar o detector.

## Reproduzir

Em `frontend/`, com as dependências e o Chromium do projeto já disponíveis:

```sh
npm run test:coverage
npm run build
VITE_AIOT_ENABLED=true npm run test:e2e -- digital-twin.spec.ts twin-experiment.spec.ts --workers=1
```

Para a medição isolada, gerar o comparador otimizado e servir **esse diretório**:

```sh
node --input-type=module -e "import {build} from 'vite'; await build({build:{outDir:'/tmp/coldsafe-rd09-dist',emptyOutDir:true,rollupOptions:{input:'experiments/rd02/index.html'}}})"
npm exec vite -- preview --host 127.0.0.1 --port 4175 --strictPort --outDir /tmp/coldsafe-rd09-dist
```

Em outro terminal, usar uma pasta de saída existente **nova** para preservar as
evidências desta entrega; informar hardware/build reais. Não rodar cargas GPU
concorrentes durante a medição:

```sh
RD02_BASE_URL=http://127.0.0.1:4175/experiments/rd02/ RD02_OUTPUT=/tmp/nova-medicao RD02_HARDWARE='identificar hardware' RD02_BUILD='identificar build' node experiments/rd02/benchmark.mjs
RD02_BASE_URL=http://127.0.0.1:4175/experiments/rd02/ RD02_OUTPUT=/tmp/nova-medicao node experiments/rd02/visibility-native.mjs
```

O script complementar contém asserts dos critérios e foi executado; reutiliza
Playwright somente para localizar o executável instalado, sem controlar a página
por ele. Perfil efêmero fica no diretório temporário do sistema; nenhuma credencial
ou preferência do navegador pessoal é usada. `manifest.json` registra hashes dos
arquivos de implementação/teste e evidências desta entrega.
