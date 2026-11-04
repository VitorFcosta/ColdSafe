disposition: ship

Revisão manual substituta, pelo agente principal: o subagente independente foi
interrompido por limite de uso antes do relatório final. Não é aprovação
independente. Autoridade específica: C-02/C-04, M-06 e composição P-05 aprovados;
não houve nova descoberta de identidade/PRODUCT/DESIGN/QUALITY BAR nesta migração.

## persistence

Pass no escopo documental existente: cartão RD-11, índice e evidências locais.
Capturas requeridas presentes: desktop/mobile completos e viewport, hero-repro,
diálogos desktop/mobile, título/controles a 320 px e texto 200%, dois vazios viewer.
Imagens inspecionadas; reflow final confirma fonte 32 px e scrollWidth 320. Uma
captura preliminar de texto ampliado tinha medição antes da aplicação do estilo;
foi substituída após exigir a precondição de 32 px no teste.

## fidelity

| Elemento | Veredito e evidência |
| --- | --- |
| TYPE | Match: Inter e escala/tokens existentes; cabeçalhos, labels persistentes e campos legíveis. |
| MATERIAL | Match: superfícies claras e controles planos da referência; nenhuma imagem substitui comportamento. |
| GROUND | Match: canvas #f3f6f5, superfícies #ffffff e petróleo; paleta presente na captura final. |
| Desktop | Match: ambientes à esquerda, dispositivos e três limites à direita; ações junto do objeto. |
| Celular | Match: ambiente/seletor, dispositivos e limites; resumo de faixa/margem e edição em continuação. |
| Adicionar dispositivo | Adaptation: acionador permanece no cabeçalho do próprio objeto em ambas as larguras, sem duplicar controles; respeita a ordem M-06. |
| Confirmação | Adaptation: `<dialog>.showModal()` conforme C-04, alvo/MQTT/consequência, Cancelar inicial, Escape e retorno/fallback. |
| Viewer/vazio | Match: consulta e explicação, sem formulário, ação proibida ou convite imperativo para cadastro. |
| Campos e restrições | Match: nome120/MQTT64 imutável; três limites e ajuda; validação textual, rascunhos e foco. |

## ceiling

Reached para o modo Operate e recorte M-06: hierarquia, contexto, seleção e ações
distintas, nomes longos/IDs com quebra e modal rolável. Não foi inventada identidade,
ornamento, função de reativar/excluir/mover nem edição de MQTT.

## material_fixes

- Resolved: achado parcial do revisor independente — botão “Renomear” tinha nome
  acessível “Editar ambiente”. Os dois acionadores agora usam “Renomear ambiente
  [nome]”; unit e E2E por nome acessível aprovados. Nenhuma mudança visual adicional.
- Clear no restante do recorte conferido manualmente; detector único sem achados.
  O modal de texto ampliado rola internamente: título e controles têm capturas
  separadas, Cancelar com foco e visível. Sem auditoria de leitor de tela real nesta RD.

## keep

Preservar a seleção própria da Gestão, os rascunhos RD-05, o catálogo autorizado,
a diferença entre salvar e consultar e a desativação sem comando físico.
