# RD-18 — fechamento complementar de 03/11/2026

Ocultar/mostrar dados ao vivo nas quatro telas, mantendo design system, coleta,
autorização e ACK. VoiceOver dispensado pelo usuário; árvore AX não valida fala.

- [Resultado e limites](verification.json), [lista exata de arquivos](changes.json)
  e [manifesto de integridade](manifest.json).
- [125 testes focados](unit-focused.log), [757 testes e cobertura](coverage.log)
  e [RED antes da implementação](unit-red.log).
- [169 E2E aprovados / 42 pulados no legado](e2e-legacy-final.log) e
  [42 aprovados no AIoT](e2e-aiot.log): 211 casos distintos, HTTP/WS controlados.
  Os 12 novos cenários cobrem as quatro telas, 320 px/texto 200%, teclado/AX,
  atualização oculta, ACK sem segundo POST, escopo, revogação e cena.
- Falhas intermediárias: [primeiro viewport](e2e-legacy-initial.log) e
  [corrida de identidade](e2e-legacy-identity-race.log). Ajuda encurtada no primeiro;
  no segundo, espera pela consulta assíncrona. Asserções de segurança preservadas.
- Builds [AIoT](build-aiot.log), [legado](build-legacy.log),
  [Docker final](docker-build.log), [frontend retomado](docker-frontend-up.log)
  e [núcleo retomado](docker-core-up.log). O núcleo estava parado antes da retomada;
  volumes preservados. Reiniciar o simulador reinicia seu desgaste em memória.
- [Smoke autenticado real nas quatro rotas](runtime-authenticated.json) e
  [containers](docker-state.json): 12 principais saudáveis, Ollama/coordenador
  parados. Seis sensores recentes, estados legítimos pending/persisted e previsão
  com versão anterior observados. Nenhum comando de atuador enviado nesse smoke.
- [Inspeção controlada](visual-checks.json), [estilos autenticados](styles-authenticated.json)
  e [contraste](contrast.json): 6,19:1 no botão e 5,17:1 na ajuda. O fundo da ajuda
  não foi medido corretamente no script inicial; descartado esse campo, usando
  a medição autenticada separada do ancestral opaco real.
- [Detector Impeccable](detector.json): zero achados determinísticos; não é selo
  estético ou certificação de acessibilidade.

Capturas com dados simulados: [dashboard desktop](dashboard-1440.png),
[Insights desktop](insights-1440.png), [gêmeo desktop](digital-twin-1440.png),
[Mensageria desktop](messaging-1440.png); [dashboard320](dashboard-320.png),
[Insights320](insights-320.png), [gêmeo320](digital-twin-320.png),
[Mensageria320](messaging-320.png) e [gêmeo oculto](twin-hidden-320.png).
A fonte do controle foi conferida em 28 px antes das capturas móveis.
Elas não representam telefone físico ou dados pessoais reais.

Nenhuma dependência nova. Sem participantes, VoiceOver atual, Safari/Firefox,
calibração física ou aprovação do assistente. Os registros antigos do diretório
superior permanecem históricos e não foram substituídos.
