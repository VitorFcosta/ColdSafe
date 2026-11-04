# RD-18 — Verificação integrada, encerrada por aceite com ressalvas

Rodada de **02/11/2026**, base Git `27bba6f`, árvore local preexistente preservada.
Após a rodada, o usuário autorizou registrar o cartão como feito. RD-18 foi
encerrada por esse aceite, com ressalvas: falta implementar o controle da
apresentação de dados automáticos e validar a rodada atual com leitor de tela.
Não houve implementação ou teste novo nesse encerramento documental.
O [checkpoint](../../tasks/RD-18.md#checkpoint) é a fonte do estado e dos testes.

## Evidência nova desta rodada

| Artefato | Alcance |
| --- | --- |
| [coverage.log](coverage.log) | 755 testes/53 arquivos; denominador original de features/views. |
| [build legado](build-legacy.log) / [build AIoT](build-aiot.log) | Tipagem/build com flag false/true, sem suprimir aviso do chunk 3D. |
| [E2E legado](e2e-legacy.log) | 169 aprovados, 30 pulados; os pulados pertencem à flag AIoT. |
| [E2E AIoT](e2e-aiot.log) | 30 cenários com HTTP/WS controlados; inclui novo C-11 e WebGL real. |
| [Confirmação do foco](focus-repeat.log) / [ordem final](focus-order-confirm.log) | 6/6 repetições e 2/2 na versão final após consolidar fonte/layout; histórico de falhas permanece no checkpoint. |
| [Manifesto](manifest.json) | Arquivos alterados/criados e hashes; 969 preexistentes fora do escopo preservados. |
| [Verificação](verification.json) | 199 cenários distintos aprovados nas duas flags; encerramento por aceite com ressalvas técnicas. |
| [Matriz C-01 a C-11](scenarios.json) | Specs e fronteira de integração; não é estudo de descoberta por pessoas. |
| [Estilos computados](rendered-styles.json) / [contraste](contrast.json) | 27 pares textuais desta rodada, mínimo 5,10:1; recorte, sem WCAG integral. |
| [Reuso RD-09](rd09-reuse.json) | Hashes de fontes de render/modelo/experimento idênticos ao manifesto histórico; nenhum novo benchmark. |
| [Tentativa de leitor de tela](screen-reader-attempt.json) | Ativação/fala não confirmada. Árvore AX do login não conta como teste VoiceOver. |

Capturas selecionadas das execuções atuais, todas com dados simulados:

- [Visão geral desktop](dashboard-desktop.png): seis grandezas, histórico e previsão sintética.
- [Insights em 320 px/texto 200%](insights-320-text-200.png): cabeçalho e seletores; conteúdo continua por rolagem.
- [Gêmeo em celular](twin-mobile.png): canvas 3D real com seleção e pausa da animação; não é imagem usada no produto.
- [Confirmação de Gestão](manage-dialog-mobile.png): diálogo nativo, fundo inerte, foco na ação segura.
- [Tabela de Mensageria](messaging-table-focus.png): foco na região rolável; métricas globais e amostras privadas.
- [Assistente em 320 px](assistant-320-incomplete.png): texto a 200%, resposta incompleta, entrada focada.

Os seis PNGs foram abertos. Derivam dos specs existentes das famílias e foram
copiados para esta pasta para conservar a data/escopo da rodada integrada.
Datas/valores dentro das telas são fixtures, não horário de coleta real.
MacOS 27.0.1 arm64, Node 24.22.1 (referência do projeto 24.20.0), Chromium 153.0.8010.12.

## Ressalvas técnicas preservadas no encerramento

A pausa 3D não pausa o conteúdo atualizado por polling/WS. A ausência de controle
de pausa/frequência/ocultação para esses dados foi identificada estaticamente
em quatro vistas e encaminhada como decisão de escopo, conforme a RD-18.
[Referência primária W3C](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html).
A exceção de essencialidade não foi demonstrada; não presumir conformidade.

A leitura assistiva atual não foi validada. O leitor não foi confirmado ativo
nas tentativas CUA; não há fala/cursores/anúncios observados. O registro histórico
básico da RD-10 mantém seu próprio alcance e não é reexecução desta rodada.
A hipótese de anúncios repetidos deve ser avaliada no ensaio real, sem converter
análise estática em resultado de uso.

Sem pesquisa com participantes, celular físico, Safari/Firefox ou integração
real de API/IoT. Os oito specs `*-real.spec.ts` ficaram fora da execução comum;
não foram iniciados containers, treinamento ou comandos físicos. A mídia
pública e os benchmarks anteriores continuam evidências históricas datadas.
