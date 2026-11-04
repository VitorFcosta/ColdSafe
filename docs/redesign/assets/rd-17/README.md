# RD-17 — Apresentação pública

Evidências da implementação em **02/11/2026**, macOS 27.0.1 arm64, Node 24.22.1,
Chromium 153.0.8010.12. A página pública foi verificada com API bloqueada; os
fluxos autenticados de regressão usam respostas controladas. Sem backend real.

| Artefato | O que mostra |
| --- | --- |
| [Desktop, viewport](desktop-viewport.png) / [página inteira](desktop.png) | 1440 × 1024, texto 100%, tema/composição M-01. |
| [Celular, viewport](mobile-viewport.png) / [página inteira](mobile.png) | 390 × 844, texto 100%, narrativa e conteúdo completo. |
| [320 px, viewport](mobile-320-text-200-viewport.png) / [página inteira](mobile-320-text-200.png) | 320 × 640, texto 200%; rolável, sem overflow horizontal. O arquivo completo é muito alto: ampliar para ler. |
| Erro de vídeo: [desktop](desktop-video-error.png), [celular](mobile-video-error.png), [320 px](mobile-320-text-200-video-error.png) | Estado de erro na UI, foco em Tentar carregar vídeo. Estas capturas usam evento local não propagável; o E2E separado aborta a requisição real e comprova erro/retry/recuperação. |
| [Quadro do vídeo com legenda](video-caption.png) | Captura do player visível, após reprodução e entrega de quadro ao compositor. Mídia real local, com conteúdo de uma interface anterior e dados simulados. |
| [media.json](media.json) | 81,44 s, oito legendas verificadas em 5/15/25/35/45/55/65/75 s, reprodução avançando e pixels decodificados. |
| [desktop.json](desktop.json), [mobile.json](mobile.json), [320 px JSON](mobile-320-text-200.json) | Viewports, fonte e cores computadas. |
| [contrast.json](contrast.json) | 30 pares: oito textos e dois fundos de foco por viewport. Texto mínimo 5,17:1. Não certifica WCAG integral. |
| [detector.json](detector.json) | Única execução do detector Impeccable: `[]`. |
| [verification.json](verification.json) | Ambiente, resultados e hashes da mídia preservada/ilustração copiada. |

Os dez PNGs foram abertos. As capturas do topo e da página inteira são da nova
página, não mockups; a [composição P-05](../compositions/01-apresentacao.png) é
referência visual aprovada. Movimento reduzido ativo nas capturas de layout.

Uma primeira captura de reprodução fora de viewport tinha fundo preto apesar
do tempo/legenda avançarem. Foi descartada e substituída: o teste agora traz o
player à tela antes de reproduzir, espera `requestVideoFrameCallback` e verifica
que o quadro decodificado contém a interface clara. O JSON registra 175 pixels
claros em uma amostra de 192, acima do mínimo 96; isso não é benchmark.

O vídeo original, sem áudio, e seu VTT **não foram regravados**. Foram conferidos
por decodificação integral ffmpeg, oito quadros e oito cues ordenadas no VTT,
além da reprodução no navegador. A mídia continua sendo evidência histórica de
uma versão anterior com HTTP simulado, documentada em setembro de 2026; não
comprova a pilha AIoT atual ou hardware físico.

A ilustração distribuída em `frontend/public/media/equipamento-conceitual-p05.png`
é cópia de pixels idênticos do [asset aprovado](../compositions/equipamento-conceitual-p05.png).
Origem, geração em 28/10/2026 e prompt estão na
[estratégia P-05](../../compositions/3d-strategy.md#ilustração-usada-nas-composições).
Não foi selecionado asset externo novo nem substituída a cena 3D real.

Para recriar capturas em `frontend/`, com Node/Chromium do projeto disponíveis:

```sh
RD17_CAPTURE=1 VITE_AIOT_ENABLED=false npm run test:e2e -- landing.spec.ts --workers=2
```

Saída em `.impeccable/review/rd-17/` na raiz, ignorada pelo Git. Sem a variável,
o spec verifica os fluxos sem regravar estes artefatos documentais. Consulte o
[checkpoint](../../tasks/RD-17.md) para os demais comandos e limitações.
