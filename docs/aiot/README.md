# Retomar a evolução AIoT

## Situação em 17/10/2026

O código continua na base v1/v2 descrita no [README](../../README.md).
O contrato v3 foi fechado; migrações 004–006 e metadados privados estão preparados.
O simulador MQTT v3, gateway MQTT/AMQP e gravador InfluxDB estão implementados;
API, regras de temperatura e entrega WebSocket v3 estão implementadas na B2-13;
dashboard v3 está integrado na B2-14; demais consumidores continuam posteriores.
O [índice de tarefas](tasks/README.md) e cada cartão são o registro de execução.

A última entrega foi [B2-19](tasks/B2-19.md): Laboratório Web para geração privada,
acompanhamento recuperável por UUID, configuração/autor e qualidade observada,
com amostra separada de dez linhas. Chromium/HTTP/PostgreSQL/RabbitMQ reais
comprovaram geração de um milhão, recarga sem reenvio, isolamento e falha parcial
sem dataset concluído. Resumo/amostra verificam todos os blocos por consulta;
há custo de I/O proporcional ao volume. Sem nova dependência ou ativação pessoal.

A [B2-18](tasks/B2-18.md) conserva gerador NumPy offline em blocos
de 50 mil, integrado ao worker de jobs e volume persistente privado. Foram
verificadas 1–2 milhões de linhas, reprodução por seed/hash, ruído/faltantes/
outliers, degradação e RUL censurada sem labels no live. Pico RSS medido:
82–89 MiB no Mac e 91,4 MiB no container no teto, sem extrapolar à pilha final.
Retomada repete deterministicamente em diretório exclusivo por tentativa;
órfãos exigem limpeza manual. Overlay pessoal não ativado. Detalhes/testes no cartão.

A [B2-17](tasks/B2-17.md) conserva infraestrutura de jobs privados,
POST administrativo `202`, outbox AMQP, workers com lock PostgreSQL único,
checkpoints/retomada e progresso HTTP/SSE autenticado por dono. PostgreSQL/RabbitMQ
reais e executores pequenos comprovaram assincronia, isolamento, concorrência,
duplicatas e retomada; geração massiva agora usa B2-18, ML continua posterior.
Treino sem handler real termina failed explicitamente. Overlay pessoal não ativado. Exclusão
depende da sessão PostgreSQL viva; ver limites de coordenação/recuperação no cartão.

A [B2-16](tasks/B2-16.md) conserva observador em fila dedicada e resumos
privados de últimas mensagens/DLQ na Mensageria. API valida o proprietário atual
no PostgreSQL; leitura não retira originais das filas de negócio/DLQ. Ensaio real
e Chromium passaram com backlog durante parada, esvaziamento na retomada,
persistência exata, mensagem inválida preservada e isolamento de contas.
Amostras são limitadas/em memória; não importam itens antigos da DLQ. Parada/retomada
seguem manuais no terminal. A ativação pessoal desta entrega não foi executada.

A [B2-15](tasks/B2-15.md) conserva nove filas e métricas globais administrativas
via API ColdSafe, usando credencial exclusiva de monitoramento.
`consumers` conta assinaturas do broker; serviços por polling podem mostrar zero
mesmo funcionando. A ativação local foi autorizada e concluída depois da entrega:
credenciais ausentes preenchidas, conta existente admin e serviços atualizados
com `compose.messaging.yaml`, preservando o dashboard e volumes. Detalhes no cartão.

A B2-14 conserva dashboard com seis medições, gráfico/tabela por grandeza,
histórico/recuperação REST v3, LED com confirmação separada do estado observado
e buzzer automático. Seu percurso real do simulador a 1 Hz permanece evidência
datada no cartão; não foi reexecutado como parte do aceite B2-15.

A B2-12 conserva gravador que consome fila própria e grava
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
simulador ainda são em memória. A B2-13 isola status/timeout v3 do legado e
mantém o catálogo comissionado de um equipamento por runtime. A B2-09 conserva
sensores/desgaste; B2-08, frontend estático/proxy. A integração do dashboard
v3 está concluída no escopo B2-14. O próximo cartão é [B2-20](tasks/B2-20.md), somente após
escolha do usuário; não iniciá-lo automaticamente.

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
