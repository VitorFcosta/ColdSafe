# RD-10 — Evidências da página e inspeção

31/10/2026. Base Git `27bba6f`, com trabalho local anterior preservado. A P-05
orienta a composição; suas imagens não foram reutilizadas como prova funcional.

## Verificações executadas

| Evidência | Resultado e alcance |
| --- | --- |
| [coverage.log](coverage.log) | 693 testes/53 arquivos; statements 94,81%, branches 91,05%, functions 92,44%, lines 97,57%. Mesmas inclusões/exclusões anteriores. |
| [build.log](build.log) | Tipagem e build finais aprovados. Chunk do gêmeo 598,55 kB / gzip 154,69 kB; aviso acima de 500 kB preservado. |
| [regression-e2e.log](regression-e2e.log) | Oito casos do gêmeo no código final: nove seleções por WebGL, WS/REST, expiração, contexto, fallback, teclado, LED/ACK/rejeição/timeout, viewer, pausa e redução. |
| [composition-e2e.log](composition-e2e.log) | Dois casos RD-10 em 1440/390 px: ordem, grandezas/unidade/zero, previsão separada, leitura selecionada, link interno e reflow a 320 px/texto 200%. |
| [shell-context-e2e.log](shell-context-e2e.log) | 38 casos: papéis, shell, navegação e contexto, URL, conta, dados antigos, revogação e celular. |
| [reflow.json](reflow.json) | Viewport/scrollWidth 320, fonte raiz 32 px. Elementos da tabela podem ser mais largos dentro da região própria com rolagem, sem ampliar a página. |
| [contrast.json](contrast.json) | Pares sRGB dos estilos: texto principal 14,34:1; secundário 5,62:1 em branco/5,17:1 no canvas; seleção/link 5,36:1; crítico 6,47:1; conectado 5,93:1; foco 6,26:1. Método/limites no JSON. |
| [detector.json](detector.json) | Uma execução Impeccable nos alvos: nenhum achado. Não foi reexecutado após o ajuste de proporção. |

São **48 E2E distintos**, executados em três comandos, sem somar repetições para
inflar a contagem. Playwright/Chromium 153, Node 24.22.1 do runtime disponível
(package.json pede 24.20.0); nenhum pacote instalado/atualizado. HTTP/WS são
respostas controladas; o WebGL dos E2E é real, inclusive perda de contexto.
Não é evidência de backend/IoT real, GPU móvel física ou novo benchmark da cena.

## Capturas e revisão visual

- `desktop.png`/`mobile.png`: páginas completas, corrente do motor selecionada.
- `desktop-viewport.png`/`mobile-viewport.png`: primeiro enquadramento, desde o topo.
- `scene-list-desktop.png`/`scene-mobile.png`: cena, seleção e pausa.
- `hero-repro.png`: enquadramento desktop para comparar com M-05/P-05.
- `mobile-320-text-200.png`: foco na corrente, ID completo com quebra de linha.

A cena nas imagens é uma captura do canvas Three.js, sem usar uma imagem como
implementação. Há somente uma leitura na fixture de histórico; o gráfico mostra
um ponto, sem inventar curva contínua. O desktop também mostra temperatura zero
válida/crítica conforme limites atuais; a leitura corrente selecionada continua
1,4 A. Previsão é do equipamento, nunca do sensor selecionado.

Revisão independente por `a11y-architect`, substituto explícito do perfil finish
Impeccable específico indisponível: composição e acessibilidade estática aceitas;
um P2 de pé frontal cortado. Correção só no pai: limitar a largura da área 3D na
mesma escala de sua altura, sem editar câmera/modelo da RD-09. Novas capturas nos
mesmos arquivos e confirmação do revisor: **P2 resolved; disposition ship para a
revisão visual**. A confirmação revisou o achado, sem nova busca de defeitos.

## Leitor de tela: o que foi efetivamente verificado

[screen-reader.json](screen-reader.json) é o registro manual normalizado dos
retornos da árvore nativa/CUA, não uma transcrição de áudio. VoiceOver real no
macOS 27.0.1 foi ativado pelo diálogo nativo e confirmado pelo processo/ajuste
`AX_VOICEOVER_ENABLED=on`. Em navegador de teste isolado, com WebGL indisponível,
Tab/Enter percorreu os nove botões; cada um ficou pressionado, manteve foco e
atualizou o título/ID e a grandeza do detalhe. A leitura expirou durante o ensaio;
isso preservou inventário/histórico e ocultou valores atuais. Zero POST de atuação.

**Limite:** áudio dos anúncios não auditado/capturado; ativação por atalhos próprios
do VoiceOver não foi validada pela automação. Esse teste básico com leitor ativo
não comprova a qualidade da fala, navegação completa pelo rotor nem conformidade
WCAG integral. Sem participantes de pesquisa. O VoiceOver foi restaurado para
`off` nos Ajustes e os utilitários/tutorial/browser temporários foram encerrados.
O [guia oficial da Apple](https://support.apple.com/en-ae/guide/voiceover/cpvokys01/10/mac/27)
foi consultado para os atalhos durante o diagnóstico, sem tratá-lo como prova da execução.

## Reproduzir os testes

Em `frontend/`, com dependências/Chromium já disponíveis, usar Node do projeto:

```sh
npm run test:coverage
npm run build
VITE_AIOT_ENABLED=true npm run test:e2e -- digital-twin.spec.ts --workers=1
VITE_AIOT_ENABLED=true npm run test:e2e -- app-shell.spec.ts monitoring-context.spec.ts --workers=1
```

Os testes RD-10 salvam as capturas em `.impeccable/review/rd-10/`; cópias desta
entrega ficam aqui. O ensaio nativo reutilizou as mesmas fixtures HTTP/WS num
runner temporário, sem mudar a aplicação para expor dados de teste. Seu registro
não substitui os comandos automatizados. `manifest.json` conserva hashes dos
arquivos alterados/evidências e a preservação dos demais arquivos anteriores.
