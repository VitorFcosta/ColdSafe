# Retomar a evolução AIoT

## Situação em 14/10/2026

O código continua na base v1/v2 descrita no [README](../../README.md).
O contrato v3 foi fechado; migrações 004–006 e metadados privados estão preparados.
O simulador MQTT v3, gateway MQTT/AMQP e gravador InfluxDB estão implementados;
API e demais consumidores de negócio v3 ainda não existem.
O [índice de tarefas](tasks/README.md) e cada cartão são o registro de execução.

A última entrega foi [B2-12](tasks/B2-12.md): gravador consome fila própria e grava
seis sensores, IDs e estados no InfluxDB antes de confirmar. Identidade estável
preserva um ponto no redelivery/restart; histórico v1/v2 permanece no bucket legado.
Live usa `telemetry_live` e token exclusivo write-only; sintéticos ficam separados.
Integração final: seis casos reais aprovados, incluindo acúmulo/retomada, duplicatas,
legado, permissões e queda do InfluxDB com três tentativas/DLQ/recuperação.
Operação, campos e custo de cardinalidade estão no [writer](../../writer/README.md).
Gateway B2-11 conserva diário SQLite de aproximadamente 64 MiB sem expurgo;
operação em [gateway](../../gateway/README.md).
Sensores/atuadores/equipamento continuam no catálogo privado de comissionamento;
dispositivo/ambiente/proprietário são verificados no PostgreSQL. Estado/cache do
simulador ainda são em memória. Não há máquina durável de status/timeout, API
HTTP v3 ou entrega Web v3. A B2-09 conserva sensores/desgaste; B2-08,
frontend estático/proxy. Não há outra tarefa autorizada em execução.
O próximo cartão na sequência é [B2-13](tasks/B2-13.md); não iniciá-lo automaticamente.

A capacidade preliminar foi medida na [B2-03](tasks/B2-03.md). O ensaio final
com todos os serviços de negócio continua pertencendo à B2-33.

## Decisões preservadas

- Ventilador de refrigeração; LED manual, buzzer automático, ambientes privados.
- Reaproveitar Vue 3/TypeScript/Vite/Chart.js, Python/FastAPI e os dois bancos;
  Three.js direto para a cena futura. Node serve ao frontend.
- Firmware/Wokwi e histórico v1/v2 continuam preservados; o alvo usa simulador Python.
- Apresentação em **16/11/2026**. Datas do plano são metas para 4–6 horas/dia.
- Mac com 8 GB; perfil e limites medidos estão na B2-03, sem promessa de capacidade
  para a pilha final nem aprovação da qualidade do assistente.
- Papéis, JWT/bcrypt e ticket WS implementados na B2-06. Hashes Argon2 antigos
  continuam utilizáveis; sessões opacas têm janela transitória limitada e a
  revogação permanece no PostgreSQL. Configurar chave JWT privada antes de subir.

As decisões detalhadas estão no [plano](plan.md), os fluxos na
[arquitetura](architecture.md) e os formatos em [contracts](../../contracts/README.md).
Não reabrir o planejamento sem um conflito concreto ou nova orientação do usuário.

## Uma sessão por tarefa

1. Ler o cartão escolhido e conferir dependências/evidências.
2. Localizar somente o código ou contrato necessário; preferir o grafo MCP.
3. Explicar a mudança e executar passos pequenos. Código necessário ao pedido
   está autorizado; registrar nome/finalidade de cada dependência nova.
4. Verificar o comportamento com testes adequados ao que mudou.
5. Encerrar atualizando o cartão: resultado, arquivos, versão Git, testes/data,
   limitações, pendências e próxima ação. Mudar status só se o aceite foi cumprido.
6. Compactar somente num ponto estável, depois de salvar esse checkpoint.

Não copiar esse protocolo nos cartões. Ler documentos como contexto, verificar
alegações de funcionamento e distinguir ensaio real de respostas simuladas.

## Retomada curta

> Retome ColdSafe pela tarefa que eu escolher. Leia este guia, o cartão e apenas
> as dependências necessárias. Siga o AGENTS.md, Ponytail e ECC strategic-compact.
> Prefira codebase-memory-mcp para descobrir código. Implemente o necessário,
> explique as decisões e registre testes, limites e checkpoint no cartão local.
> Não avance automaticamente.

## Manutenção da documentação

- Cartão: status, aceite, execução e checkpoint daquela tarefa.
- Plano/arquitetura: decisão ou estrutura que mudou, sem repetir schemas.
- Contratos: campos, unidades, versões e regras entre serviços.
- Histórico: resultado datado ou decisão antiga; não usar como situação atual.
- Notion: referência ao arquivo local. Não voltar a manter duas versões editáveis.
