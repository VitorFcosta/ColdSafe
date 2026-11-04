# Etapa 1 — Baseline: tentativa bloqueada na pré-checagem

**Data:** 04/11/2026, America/Sao_Paulo. **Resultado:** não apta para avançar.
**Escopo autorizado:** somente estado atual e baseline de 900 s, intervalo de
5 s, sem carregar modelo. **Executado:** pré-checagem e inventário de encerramento;
nenhuma série de 15 minutos iniciada, zero intervalos cronometrados.

## Decisão e motivo da interrupção

O [roadmap](../../aiot/assistant-metal-roadmap.md) exige interromper diante de
alerta de bateria baixa, suspensão ou troca de alimentação. A primeira consulta
`pmset -g batt` já informou **10%, Battery Power, discharging e Battery Warning:
Early**. Esse aviso bastou para impedir o início da janela. Não se esperou uma
queda adicional nem se tentou melhorar o resultado alterando as condições.

Durante o inventário para documentar a tentativa, às **15:45:19 -03:00**, o
sistema informou **AC Power, 12%, AC attached; not charging**. A origem da mudança
não foi determinada; o agente não conectou alimentação nem alterou configuração.
Estar com carregador conectado, mesmo sem carregar naquele instante, também
descumpre a condição de ensaio fora da tomada. Os dois estados não compõem uma
baseline contínua e não serão agregados como uma rodada válida.

Não houve mudança operacional para contornar os impedimentos. O próximo passo
é o usuário escolher repetir **a etapa 1**, em outra rodada fora da tomada,
sem alerta de bateria baixa e mantendo seus apps e configurações habituais.
Esta tentativa não autoriza a etapa 2 nem demonstra reprovação do modelo.

## Fatos observados

As saídas, horários, comandos, códigos de retorno e limites estão no
[preflight.json](preflight.json). O inventário começou às 15:45:18; seu término
está no JSON. Os comandos são sequenciais, portanto não são um retrato atômico.
A primeira pré-checagem ocorreu antes de 15:44:16, mas sua saída não contém
timestamp por comando: essa lacuna foi mantida, sem inventar horário exato.

| Item | Primeira pré-checagem | Inventário de encerramento |
| --- | --- | --- |
| Hardware | Apple M1; 8.589.934.592 bytes = 8 GiB físicos | Mesmo hardware; macOS 27.0.1, build 26A434 |
| Alimentação/bateria | Battery Power; 10%; aviso Early | AC Power; 12%; conectado, sem carregar naquele instante |
| Economia de energia | `lowpowermode 0` em bateria e AC | `lowpowermode 0` em bateria e AC; sem alteração pelo agente |
| Pressão de memória | `kern.memorystatus_vm_pressure_level: 2` | Mesmo valor bruto `2` |
| Saída de `memory_pressure -Q` | 32% no indicador de memória livre da ferramenta | 38% no indicador da ferramenta |
| Swap utilizado | `2381.44M` de `3072.00M`, conforme `sysctl` | `2477.88M` de `3072.00M`, conforme `sysctl` |
| Espaço disponível no volume do projeto | 22.925.996 KiB, cerca de 21,86 GiB | 22.926.808 KiB, cerca de 21,86 GiB |
| Containers ColdSafe | Todos os 16 parados | Todos os 16 parados; metadados selecionados registrados |
| Docker Model Runner | Runtime e backend em execução; inventário/residência vazios | Mesma condição nas consultas de status/lista/residência |

O valor `2` é interpretado como aviso de pressão: o
[handler XNU da Apple](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus_notify.c)
converte o nível interno para constantes de notificação, e o
[header de eventos](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/event_private.h)
define aviso como `0x00000002`. A consulta é a uma interface privada; as fontes
consultadas são da árvore `main`, não uma auditoria do binário instalado. Não
se confundiu esse código com a enumeração interna de pressão. Duas observações
esparsas não comprovam aviso contínuo por 60 s, nem medem sua duração.
O percentual de `memory_pressure -Q` não substitui esse nível e não significa
que 38% da RAM esteja livre para um novo modelo.

O inventário de processos encontrou, entre outros, Chrome, Safari, WhatsApp,
Mail, Calendar, Notes, ChatGPT, Terminal, Docker e componentes Codex. A lista
completa de nomes `.app` está no JSON e inclui agentes de fundo. Não foram
retidos títulos de janelas, URLs, mensagens ou argumentos dos processos. Nomes
de processos não provam janelas visíveis, que sejam todos os apps habituais,
ou responsividade. Nenhum aplicativo foi fechado ou alternado pelo agente.

## Serviços, versões e limites

- Docker Desktop **4.66.0**; Engine **29.3.0**; DMR cliente **1.1.5**, servidor
  **1.1.1**. Backend anunciado: `llama.cpp latest-metal`, `ac4cdde`, digest
  `sha256:aa3e239c5737a7fa56f3908a865eb75dfae214b9cfec2cdd929e4d5353c2d714`.
  É disponibilidade anunciada, sem comprovação de uso Metal por inferência.
- Docker anunciou **6.212.268.032 bytes = 5,7856 GiB** e 8 CPUs na VM. Isso é
  capacidade anunciada, **não consumo instantâneo** do Docker, da VM ou de modelo.
  Não se executou `docker stats` nem se atribuiu essa capacidade ao orçamento DMR.
- Ollama parado: limite registrado no container **3.489.660.928 bytes = 3.328
  MiB**, com `MemorySwap` **6.979.321.856 bytes**. Ambos são configuração, não
  uso observado; o segundo não é swap atualmente utilizado. O Compose local
  conserva `mem_limit: 3328m` e contexto 1.024; hash e trecho registrados.
- Os limites de todos os containers estão no JSON. Valor de memória `0`
  representa ausência de teto explícito nesse campo, não consumo zero.
- Saídas antigas `137` e `2` foram registradas; `OOMKilled` estava falso nos 16
  containers. Código 137 isolado não comprova OOM nem ocorrência nesta tentativa.
  Containers parados não fornecem validação atual de saúde da API, bancos ou jobs.
- As listas DMR de modelos instalados e residentes estavam vazias nos instantes
  consultados. Nenhum comando de carga, inferência, descarga, geração ou treino
  foi executado. Listas vazias isoladas não são prova contínua de quiescência.

## O que não foi medido e como interpretar

**Não há baseline aprovada.** Os 900 s a cada 5 s, responsividade ao alternar apps
e abrir página, bateria inicial/final de uma rodada válida, taxas de paginação e
p95 de swap-out continuam pendentes. Não houve teste de modelo, API ou pilha ativa.
Não se afirma estabilidade, disponibilidade de RAM ou espaço suficiente para o
download candidato. O orçamento de disco pertence à etapa 2.

`vm_stat` foi lido uma vez no inventário com timestamp, conservando contadores
acumulados e páginas de 16.384 bytes. Taxa futura deve usar dois contadores do
mesmo tipo e condição: `delta_paginas × 16384 / 1048576 / delta_segundos`, em
MiB/s. `Pageins/Pageouts` e `Swapins/Swapouts` devem ser separados; page-in não
é sinônimo de swap-in. Em intervalos exatamente de 5 s, uma página corresponde
a **0,003125 MiB/s**; a resolução efetiva depende do intervalo real registrado.
Aqui as taxas e o p95 estão **não medidos/null**, nunca zero. Não há limiar
comparativo de p95 congelado para o candidato.

Swap ocupado é um estoque, não uma velocidade. Os valores de momentos e fontes
de alimentação diferentes não fundamentam uma taxa atual, crescimento sustentado
ou causalidade. É hipótese que a carga habitual dispute memória com um 3B; não
há medição para afirmar que ele caberá ou falhará, nem que Metal resolverá isso.
As observações históricas do roadmap continuam históricas.

## Preservação, verificações e checkpoint

- Somente leituras nativas e comandos Docker de consulta. Sem instalação,
  dependências, downloads, início/parada de serviços, inferência, geração,
  treinamento, mudança de limites/energia ou acesso ao conteúdo de volumes.
- Identidades dos containers, imagens, destinos/tipos dos mounts e nomes dos
  volumes `coldsafe_*` foram registrados. Sem conteúdo pessoal, variáveis de
  ambiente, credenciais ou caminhos de origem de binds na evidência retida.
- Datasets, pesos Ollama e modelos saúde/RUL não foram abertos, apagados ou
  alterados pelo agente. A versão ativa não foi consultada em SQL: banco parado,
  sem autorização para iniciá-lo. Não houve checksum de conteúdo ou prova de
  integridade profunda dos volumes; preservação aqui é escopo das operações.
- Uma consulta de metadados falhou ao pedir `Name` de um bind mount; nova
  consulta somente de leitura omitiu esse campo e passou. O erro foi conservado;
  a saída parcial com logs antigos foi descartada para minimizar dados retidos.
  Isso foi falha da consulta de inventário, não defeito corrigido na aplicação.
- Alterações locais anteriores preservadas. Base Git identificada no JSON;
  roadmap já era arquivo local não rastreado, e sua edição foi pontual.
- Verificações executadas e aprovadas: JSON/assertions de coerência, 12 links
  locais, whitespace dos três arquivos e `git diff --check`. Hash do Compose
  permaneceu igual; entradas de alterações locais anteriores no Git preservadas.
  Comparação do roadmap com o texto anterior confirmou mudanças somente no
  cabeçalho, linha da etapa 1 e checkpoint. Revisão independente sem achados
  materiais. Essas verificações documentais não são testes de aplicação.

**Arquivos da entrega:** `preflight.json` e este `README.md`, novos nesta pasta;
`docs/aiot/assistant-metal-roadmap.md`, atualizado com status, resultado e retomada.
**Dependências adicionadas:** nenhuma. Usados Python já instalado/biblioteca
padrão e utilitários existentes. Nenhum script permanente de coleta ou integração.
**Próxima ação:** aguardar escolha do usuário para repetir etapa 1 em condições
válidas. Etapa 2 permanece pendente, sem download ou investigação de identidade
nesta tentativa. Não repetir automaticamente nem alterar critérios para aprovar.
