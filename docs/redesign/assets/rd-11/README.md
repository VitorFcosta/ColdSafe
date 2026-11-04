# RD-11 — Evidências de Ambientes e dispositivos

31/10/2026 · Base Git `27bba6f`, com alterações locais anteriores preservadas.
Referência visual: composição 06 da P-05; seus pixels não são prova funcional.

## Resultado verificado

- [coverage.log](coverage.log): **704 testes/53 arquivos**; statements 94,74%,
  branches 91,02%, functions 92,31%, lines 97,48%. Mesmas inclusões/exclusões.
- [unit-focused.log](unit-focused.log): **34 testes da Gestão aprovados** após
  correções de foco e nome acessível; fronteiras, permissões, conta, rascunhos,
  erros conjuntos e cadastro confirmado seguido de falha na consulta.
- [e2e-25.log](e2e-25.log): **25 casos distintos** aprovados, incluindo os 16
  cenários de proteção de rascunhos e 9 da Gestão. [e2e-final-9.log](e2e-final-9.log)
  repete os nove casos da Gestão após a correção do nome acessível. Não somar
  repetições como casos novos.
- [e2e-text-200.log](e2e-text-200.log): repetição dos dois casos de composição,
  exigindo fonte raiz 32 px antes de medir/capturar. [reflow-dialog.json](reflow-dialog.json):
  largura/scrollWidth 320, diálogo 288, conteúdo 286, fonte raiz 32 px.
- [build.log](build.log): tipagem/build finais aprovados. ManageView 22,91 kB,
  gzip 6,98 kB; aviso existente do chunk do gêmeo >500 kB preservado, sem relaxar limite.
- [contrast.json](contrast.json): pares dos estilos calculados por sRGB/WCAG,
  com contagem da paleta na captura. Texto principal 14,34:1, secundário ≥5,16:1,
  primária 6,19:1, desativar 6,47:1, ativo 5,93:1, foco 6,26:1. Presença da paleta
  não equivale a medir todas as adjacências/antialiasing; método no JSON.
- [detector.json](detector.json): uma execução Impeccable, sem achados. Não houve
  uma segunda execução após ajustes de foco/nome acessível.

Os E2E usam App/Router reais e HTTP controlado em Playwright/Chromium. Nenhum
backend, credencial ou dispositivo IoT real foi alterado. Node disponível24.22.1,
package.json pede24.20.0; nenhum pacote instalado ou atualizado.

## Capturas

`desktop.png`/`mobile.png`: página completa; `*-viewport.png`: início da página;
`hero-repro.png`: enquadramento desktop para comparação M-06. O foco no h1 é o
foco real de chegada pela rota, não uma borda decorativa.

`dialog-desktop.png`/`dialog-mobile.png`: alvo, MQTT e Cancelar com foco. A 320 px
com texto a 200%, `dialog-320-text-200-title.png` mostra o topo e
`dialog-320-text-200.png` os controles após rolagem interna; Cancelar permanece
focado e visível. Não se afirma que o diálogo inteiro caiba sem rolar.

`viewer-no-environments.png`/`viewer-no-devices.png`: vazios sem controles de
escrita; limites somente de consulta quando disponíveis. São fixtures, não
inventário de uma conta real.

## Revisões e limites

Revisão independente de código encontrou dois focos incorretos e um caso residual
de retorno após falha de consulta; todos reproduzidos/corrigidos e confirmados
por testes. A revisão final dos respectivos ajustes os marcou resolved.

O subagente visual encontrou a diferença entre “Renomear” e o antigo aria-label
“Editar ambiente”, depois foi interrompido por limite de uso antes de emitir o
relatório final. Corrigido e testado. A revisão de fechamento foi substituída por
conferência manual do principal, pelo roteiro degradado Impeccable, registrada em
[review.md](review.md). **Não declarar aprovação visual independente final.**

Teclado, foco, Escape, contenção/modalidade e bloqueio de foco no fundo foram
testados no Chromium; o botão permanece Cancelar na abertura. Não houve teste
com leitor de tela real nesta RD, Safari/Firefox, celular físico ou estudo com
participantes. Não é atestado de conformidade integral.

## Reproduzir

Em `frontend/`, com dependências/Chromium já disponíveis:

```sh
npm run test:unit:run -- src/views/ManageView.spec.ts
npm run test:coverage
npm run build
VITE_AIOT_ENABLED=true npm run test:e2e -- manage.spec.ts manage-redesign.spec.ts draft-transitions.spec.ts --workers=1
```

As capturas são gravadas em `.impeccable/review/rd-11/`. O manifesto registra hashes
da implementação, testes, documentação e evidências, sem incluir a si próprio.
Nenhuma dependência nova, commit, push ou publicação.
