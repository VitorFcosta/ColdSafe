# Etapa 1 — segunda tentativa: interrompida por pressão de memória

**Data:** 04/11/2026, America/Sao_Paulo. **Resultado:** baseline não aprovada;
não avançar para etapa 2. Tentativa anterior preservada na
[pasta original](../assistant-metal-baseline-2026-11-04/README.md).

## Protocolo e execução

O usuário autorizou repetir somente a etapa 1 do
[roadmap](../../aiot/assistant-metal-roadmap.md): 900 segundos sem modelo, com
amostras a cada 5 segundos, Mac M1/8 GiB fora da tomada e apps pessoais abertos.
Foram mantidos limites, serviços e modo de energia. Antes de criar os arquivos,
o plano, a pasta separada e as regras de interrupção foram explicados.

A pré-checagem de 16:06:55 retornou bateria 40%, Battery Power, sem alerta,
pressão normal (`1`), nenhum container em execução e listas DMR vazias. Essa
consulta foi exibida no chat; o registro bruto persistido da rodada começa no
[inventário anterior](inventory-before.json), às 16:08:53.955. Não se incorporou
a consulta anterior à série nem se inventou seu timestamp por comando.

A primeira amostra, às **16:08:59.794**, já retornou pressão **`2` (aviso)**.
As 13 amostras conservaram esse valor; a última, às **16:09:59.800**, completou
**60,0049 segundos**, formando 12 intervalos de aproximadamente 5 segundos.
O coletor interrompeu com `memory_warning_60_seconds`, conforme a regra de
aviso por 60 segundos. Não foram completados os 900 segundos: faltaram
aproximadamente 14 minutos. Não houve retomada automática nem modelo carregado.

O aviso foi observado em todos os pontos de uma janela de 60 segundos; isso
satisfaz a regra operacional com resolução de 5 segundos. Não é medição contínua
entre amostras. A interpretação do valor `2` e suas fontes Apple estão descritas
no [relatório da primeira tentativa](../assistant-metal-baseline-2026-11-04/README.md).

## Resultados medidos

Saídas brutas: [samples.jsonl](samples.jsonl). Cálculos por intervalo e agregados:
[summary.json](summary.json). Resultado automático: [outcome.json](outcome.json).

| Item | Observação desta rodada |
| --- | --- |
| Alimentação | Battery Power em todas as 13 amostras; sem aviso de bateria baixa |
| Bateria | 40% inicial e final; resolução inteira do indicador não permite concluir consumo zero |
| Pressão | Aviso (`2`) em 13/13 amostras, incluindo o encerramento |
| Swap utilizado, como impresso pelo `sysctl` | `3726.88M` → `3678.88M`; redução líquida de `48.00M` |
| Disco disponível | 21.035.835.392 → 21.069.094.912 bytes, cerca de 19,59 → 19,62 GiB; mínimo 21.030.899.712 bytes |
| Containers | Nenhum em execução nos inventários e nas 3 consultas da série; os 16 existentes permaneceram parados |
| Modelos | Listas DMR de residência vazias nas 3 consultas e nos inventários; inventário de modelos instalados vazio antes/depois |
| Energia | `lowpowermode 0`; saída de `pmset -g custom` igual antes/depois e nas consultas da série |

| Taxa em MiB/s | Mediana | p95 por posto mais próximo | Máximo |
| --- | ---: | ---: | ---: |
| Page-in | 30,3747 | 76,7559 | 76,7559 |
| Page-out | 0,1565 | 0,8472 | 0,8472 |
| Swap-in | 0,2435 | 2,8952 | 2,8952 |
| Swap-out | 0 | 0 | 0 |

Cada taxa usa a diferença do contador correspondente em `vm_stat`, página de
16.384 bytes e tempo real entre as leituras: `delta_paginas × 16384 / 1048576 /
delta_segundos`. Page-in/page-out e swap-in/swap-out foram mantidos separados.
Os intervalos de relógio de parede ficaram entre **4,9952 e 5,0059 segundos**.
A resolução de uma página nas taxas ficou entre **0,0031032 e 0,0031425 MiB/s**;
em 5 segundos exatos seria 0,003125 MiB/s.

Há apenas **12 taxas por contador**. Com p95 por posto mais próximo
(`ceil(0,95 × 12)`), o p95 coincide com o máximo. Esses números descrevem apenas
o trecho interrompido, **não uma baseline estável de 15 minutos**. Seu p95 não
pode ser congelado como limiar de aceite para o candidato.

Swap-out zero e redução do swap ocupado **não anulam o aviso de pressão**.
Pressão, estoque de swap e suas taxas são observações diferentes; o critério
de parada foi acionado pelo nível de pressão, não pelo tamanho do swap.

## Condições, preservação e limites

- Apple M1, **8.589.934.592 bytes = 8 GiB** físicos. macOS, versões e backend
  anunciado estão nos inventários. Docker Desktop 4.66.0, Engine 29.3.0,
  DMR cliente 1.1.5/servidor 1.1.1 e backend anunciado `llama.cpp latest-metal`.
  Não houve inferência para comprovar Metal efetivo.
- A VM anunciou **6.212.268.032 bytes = 5,7856 GiB**, com 8 CPUs. É capacidade,
  não consumo instantâneo ou RAM livre para o modelo. Limites por container
  constam dos inventários; Ollama parado conservou **3.328 MiB**. Não se
  consultou `docker stats`; não se confundiu `MemorySwap` configurado com uso.
- Nomes `.app` foram inventariados sem títulos, mensagens, URLs ou argumentos.
  A comparação não encontrou ausência dos nomes dos apps pessoais; somente
  `ManagedClient.app` e `privatecloudcomputed.app`, componentes de fundo,
  deixaram de aparecer. A causa não foi investigada. O agente não fechou,
  alternou ou iniciou aplicativos. Processo existente não prova janela visível.
- A verificação manual de alternar apps e abrir `about:blank` foi solicitada,
  mas não há confirmação incorporada a este encerramento de 60 segundos.
  Responsividade não está aprovada. Mesmo um relato de uso normal não anularia
  o critério de pressão já acionado.
- O inventário de encerramento está em [inventory-after.json](inventory-after.json).
  Identidades/imagens/estado/limites e destinos/tipos dos mounts selecionados
  permaneceram iguais, comparando mounts sem depender de sua ordem. Nomes dos
  volumes `coldsafe_*` iguais antes/depois. `OOMKilled=false` nos 16 containers
  nos dois inventários; isso não audita OOM de todos os processos do host.
- Hashes dos Compose e dos dois arquivos da primeira evidência permaneceram
  iguais. Dados pessoais, volumes, datasets, pesos e modelos saúde/RUL não foram
  abertos, apagados ou alterados pelo agente. Sem checksum de conteúdo dos
  volumes ou consulta SQL da versão ativa; os bancos permaneceram parados.
- Sem dependências novas, instalação, download, início/parada de serviço,
  inferência, geração, treinamento, integração, commit, push ou credenciais.

O coletor desta evidência usa relógio monotônico para agendamento e detecção
automática de lacunas. A revisão apontou que isso sozinho não cobre suspensão
no macOS; foi feita auditoria adicional dos timestamps de parede contra o tempo
monotônico em **todos os 12 intervalos**. Não houve lacuna >10 s nem divergência
por intervalo >=1 s nesta rodada. Isso não comprova ausência de toda pausa curta.
O script foi preservado como executado, com hash no resumo. Antes de reutilizá-lo
em outra rodada, acrescentar a checagem de relógio de parede à interrupção em
tempo de execução; não tratá-lo como ferramenta geral já validada para suspensão.

## Verificações e decisão

O modo `--self-test` passou antes da coleta, cobrindo parsing de bateria/VM,
ausência de contadores, troca de alimentação, aviso de bateria, pressão crítica,
limite de 60 segundos e resolução. A análise conferiu timestamps, contadores
sem regressão, taxas por diferença e parada no primeiro ponto >=60 s de aviso.
O p95 foi conferido com sequência conhecida, e configurações/primeira evidência
foram comparadas por hash. São verificações do instrumento e dos documentos,
não testes de aplicação, modelo, factualidade ou capacidade da pilha.

Verificação final aprovada: os 12 intervalos e seus p95 foram recalculados,
os JSON/JSONL foram lidos, 21 links locais foram conferidos e whitespace/diff
passaram. As entradas de alterações locais no Git permaneceram iguais às do
inventário inicial. Comparação com o roadmap anterior confirmou alterações
somente no cabeçalho, linha da etapa 1 e checkpoint.

**Fato:** esta rodada chegou ao critério de pressão de aviso sem modelo carregado
pelo agente, sob condições de bateria válidas nos pontos observados. **Hipótese:**
adicionar um 3B poderia aumentar a disputa por RAM. Não se mediu esse efeito,
nem se identificou qual app provocou o aviso. Não há base para atribuir a causa
à bateria, GPU, Docker ou a um processo específico, ou para declarar que todo
ensaio futuro neste Mac falhará.

**Decisão:** não avançar à etapa 2. Aguardar a escolha do usuário entre uma nova
tentativa da etapa 1 em outro momento, mantendo as mesmas condições, ou discutir
uma revisão explícita do cenário/roadmap. Não fechar apps, aumentar limites ou
alterar energia para aprovar esta rodada; não iniciar próxima tarefa por conta própria.

## Arquivos desta entrega

- `collect.py`: instrumento de coleta somente de leitura, com autochecks; sem
  código de integração e sem chamadas de carga de modelo.
- `inventory-before.json` e `inventory-after.json`: estado, versões, apps,
  serviços, limites e hashes antes/depois.
- `samples.jsonl`: 13 amostras brutas e valores extraídos.
- `outcome.json`: parada automática e motivo.
- `summary.json`: taxas dos 12 intervalos, agregados, resolução e verificações.
- Este `README.md`: resultado, condições, interpretação, limites e retomada.
- `docs/aiot/assistant-metal-roadmap.md`: atualizado pontualmente com a segunda
  tentativa; primeira tentativa e critérios preservados.

**Dependências adicionadas:** nenhuma; Python/biblioteca padrão e utilitários
existentes. **Próxima ação:** aguardar escolha, sem etapa 2 automática.
