# Roadmap — ensaio do Llama 3.2 1B com Metal no Mac de 8 GB

**Iniciado:** 03/11/2026. **Revisão final:** 04/11/2026 (America/Sao_Paulo).
**Escolha atual:** investigar o perfil **Llama 3.2 1B Instruct Q4_K_M** no
Docker Model Runner (DMR) com Metal. O 3B deixa de ser o candidato desta rodada;
as observações anteriores sobre ele permanecem históricas. Esta revisão adapta
somente o planejamento: não executa download, carga, inferência ou integração.

**Estado operacional:** etapa 1 repetida em 04/11/2026 e **interrompida por pressão de memória**;
13 amostras/60 s em aviso, fora da tomada, bateria 40%, sem modelo carregado pelo
agente. Baseline de 15 minutos não aprovada. Somente coleta leve foi autorizada.
[Segunda tentativa e limites](../evidence/assistant-metal-baseline-2026-11-04-r2/README.md).
A [primeira tentativa](../evidence/assistant-metal-baseline-2026-11-04/README.md)
permanece preservada: bloqueada por alerta de bateria, depois observação de AC.
Etapas 2–7 continuam pendentes; sem autorização para download, configuração,
implementação ou inferência nesta entrega.

## Objetivo e limites

Medir se o **Llama 3.2 1B Instruct Q4_K_M**, anteriormente testado em Ollama
CPU, ganha viabilidade de execução no DMR/Metal, sem prejudicar os aplicativos
pessoais. Avaliar separadamente **velocidade**, **consumo/recuperação de memória**
e **qualidade factual**. O 1B já foi reprovado por fatos: a aceleração não
acrescenta capacidade ao modelo nem presume que esses erros serão corrigidos.

No Mac, o motor usa Metal nativamente; um cliente em container pode chamá-lo
por HTTP. Isso não dá acesso Metal ao container Ollama atual. CPU/GPU compartilham
os mesmos 8 GiB físicos, sem um segundo orçamento de VRAM. Não se presume ganho
de velocidade ou redução de consumo antes das medições.

- Preservar dados pessoais, volumes, datasets, modelos saúde/RUL e versão ativa.
- Manter inicialmente limites de RAM, contexto, saída e timeouts existentes.
- Não fechar aplicativos, conectar carregador ou mudar modo de energia para
  aprovar a rodada. Mudança de condição exige outra rodada identificada.
- Sem commit, push, publicação, alteração de credenciais ou uso de Notion.
- Não iniciar a próxima etapa automaticamente: registrar resultado e aguardar
  a escolha do usuário. Não adicionar ferramentas, RAG ou outro modelo ao escopo.
- O modelo 1B é o único candidato deste ensaio. Voltar ao 3B ou experimentar
  Qwen/Granite exige outra escolha e outra rodada; não substituir ao falhar.

## Conformidade com o trabalho

O [requisito R15](requirements.md) e o enunciado fornecido pelo usuário exigem
LLM local em container no Compose, sem nuvem, além de streaming, resumo pronto,
limites e auditoria. O texto exige um modelo capaz de rodar em CPU; não se deve
deduzir daí uma proibição genérica de GPU. O ponto divergente aqui é o motor
DMR no macOS **executar fora de container**, conforme a
[documentação Docker](https://docs.docker.com/ai/model-runner/#execution-environment).

As etapas 1–5 são investigação técnica isolada. Antes de integrar na etapa 6
ou adotar na etapa 7, registrar aceitação explícita do professor para essa
diferença de execução. Aprovação técnica não é aprovação do requisito escolar.
Sem essa aceitação, o experimento pode produzir dados, mas DMR/Metal nativo não
será declarado solução final conforme. Nenhum contato será feito automaticamente.

## Base da decisão: fatos e hipóteses

| Classe | Informação disponível |
| --- | --- |
| Evidência antiga | O 3B CPU expirou também na tomada e com teto temporário de 4 GiB; houve paginação intensa. 1B foi reprovado por fatos; Qwen por fatos e disponibilidade. Ver [registro do ensaio](presentation.md) e [relatório](../evidence/docker-presentation-2026-11-02/verification.json). |
| Configuração CPU preservada | O código conferido na investigação continua no perfil `llama3.2:3b-instruct-q4_K_M`, contexto 1.024, saída 256, GPU desativada, teto Ollama 3.328 MiB. Escolher o ensaio 1B não altera essa configuração. Alterações locais já existentes: preload 300 s e tolerância do healthcheck 360 s; preservá-las. |
| Observação anterior nesta conversa, sem relatório bruto novo | Desktop 4.66.0; DMR cliente 1.1.5/servidor 1.1.1; backend `llama.cpp latest-metal` disponível, inventário/residência vazios. Containers ColdSafe parados; Mac na bateria, 8 GiB físicos, VM com aproximadamente 5,79 GiB, swap utilizado próximo de 8 GiB e disco livre próximo de 12 GiB. Revalidar antes do ensaio; não são medições de inferência. |
| Identidade antiga do 3B, fora do ensaio atual | Consulta remota de `ai/llama3.2:3B-Q4_K_M` retornou `IQ2_XXS/Q4_K_M`, 3,21 B, aproximadamente 1,87 GiB; digest `sha256:436bb282b41968a83638482999980267ca8d7e8b5574604460efa9efff11cf59`. Não usar esse nome/digest para o 1B. A ambiguidade antiga não foi resolvida nem autoriza baixar esse artefato. |
| Referência histórica do 1B CPU | `llama3.2:1b-instruct-q4_K_M`, 14 perguntas com PostgreSQL/Ollama CPU reais e dados preparados: mediana de primeiro texto 2,93 s e total 6,42 s; totais entre 3,83 e 23,35 s. Primeira pergunta: 11,36 s até texto e 23,35 s total, sem medição separada de carga fria. [Saídas](../evidence/docker-presentation-2026-11-02/quality-1b-2026-11-03.json). |
| Reprovação factual do 1B | Inventou RUL de 5 h em vez de 10 h e saúde/RUL atuais para leituras antigas, entre outros erros. [Revisão independente](../evidence/docker-presentation-2026-11-02/quality-1b-independent-review-2026-11-03.json). A reprovação continua válida; ensaio Metal será nova evidência, sem apagar ou reinterpretar as respostas antigas. |
| Identidade atual pendente | O alvo é o perfil 1B Instruct Q4_K_M; tag DMR e digest ainda não foram escolhidos/verificados. Conferir pesos, tokenizer, template e quantização; priorizar reaproveitamento verificável dos pesos 1B existentes, sem alterar os blobs/volumes Ollama. Não supor equivalência por nome nem usar tag genérica. |
| Hipótese | Metal pode reduzir prefill e tempo de resposta do 1B. Não foram comprovados ganho neste Mac, margem de RAM, recuperação ou factualidade. A qualidade anterior pode continuar insuficiente mesmo com resposta mais rápida. |

Swap acumulado não mede taxa atual de paginação. Capacidade anunciada da VM
não é consumo instantâneo. Com DMR nativo, aumentar a RAM da VM não aumenta
diretamente o orçamento do modelo e pode intensificar a disputa com aplicativos.
O teto de 3.328 MiB do container Ollama não é um limite automaticamente imposto
ao motor DMR nativo. Manter as configurações existentes e registrar consumo
real do motor; não confundir teto configurado com medição ou com memória livre.

Os tempos CPU acima servem somente de referência histórica. Uma afirmação de
ganho CPU × Metal exige comparação controlada, sequencial, com condições e
perfil documentados, se o usuário escolher esse teste adicional. Não executar
Ollama e DMR simultaneamente, nem iniciar uma rodada CPU automaticamente.
Registrar mudanças de template, prompt de arquitetura, pesos ou runtime que
impeçam atribuir a diferença exclusivamente à GPU.

## Dois marcos e sete etapas

**Marco A — viabilidade isolada (1–5):** qualificar o candidato sem trocar o
provedor pessoal. **Marco B — integração segura (6–7):** somente se o marco A
justificar o esforço. Passar isoladamente não aprova a pilha inteira.
O marco B também depende da condição de conformidade escolar acima. Velocidade
aprovada com factualidade reprovada encerra o candidato, sem integração.

| Etapa / estado | Objetivo e pré-requisito | Trabalho e evidência esperada | Aprovação / ação se falhar |
| --- | --- | --- | --- |
| **1. Baseline — interrompida por pressão (04/11, rodada 2)** | Nova rodada válida necessária antes de carregar o 1B Metal. | M1/8 GiB, 40% fora da tomada; 13 amostras/12 intervalos de 5 s, aviso em todos os pontos de 60 s. [Relatório e saídas](../evidence/assistant-metal-baseline-2026-11-04-r2/README.md). Parada automática conforme critério; taxas do trecho calculadas, sem baseline estável nem aceite de responsividade. Primeira tentativa preservada. Em repetição escolhida pelo usuário: 15 min/5 s sem modelo e verificação de responsividade; detectar suspensão por relógio de parede e monotônico antes de reutilizar o coletor. | Não apta para avançar. Não ignorar o aviso porque o novo candidato é 1B ou usa GPU; não usar p95 do trecho em aviso como limiar do candidato. |
| **2. Identidade do 1B — pendente** | Baseline apta; escolher artefato correspondente ao perfil 1B anterior. | Conferir origem/licença, variante Instruct, Q4_K_M, digest dos pesos, tokenizer/template, compatibilidade DMR e espaço para importação/download/cache. Fixar versão do backend. Verificar se os pesos existentes podem ser reutilizados sem alteração; importar/baixar somente o artefato escolhido em etapa autorizada, sem apagar os anteriores. | Identidade e orçamento de disco documentados. Se houver diferença de quantização/pesos/template, registrar e pedir escolha antes de carregar; não alegar comparação do mesmo perfil nem voltar ao 3B por padrão. |
| **3. Lifecycle isolado — pendente** | Identidade confirmada; runtime dedicado durante a rodada. | Preparar cliente mínimo descartável, sem credenciais/volumes pessoais e sem serviços ColdSafe pesados. Testar parser/limites com respostas controladas antes da chamada real. Uma carga, uma pergunta representativa, conclusão e descarga; depois cancelamento delimitado. Registrar requisições, término, residência e memória sem dados pessoais. | Metal efetivo confirmado por evidência do motor, contexto configurado, resposta válida e descarga comprovada. Se carga/descarga ficar ambígua, bloquear novas chamadas e recuperar antes de continuar. |
| **4. Capacidade isolada do 1B — pendente** | Lifecycle normal/cancelamento aprovado. | Repetir três ciclos carga → pergunta → descarga. Medir primeiro texto, tempo total, pico de memória, pressão, taxas de paginação, swap ocupado, disco e bateria; separar frio de aquecido. Comparar com baseline e mediana CPU histórica de 6,42 s somente como referência. Publicar se Metal efetivo trouxe benefício observado, sem afirmar speedup causal de condições diferentes. | Atender critérios pré-fixados. Se falhar, conservar resultado e parar; não elevar RAM/timeouts. Rapidez não aprova fatos. Uma comparação CPU controlada adicional depende de escolha separada. |
| **5. Factualidade do 1B — pendente** | Capacidade aprovada; mesmo perfil/prompt, perguntas e fatos operacionais. Corrigir somente o fato de arquitetura no resumo/rubrica isolados para DMR/Metal, registrando a diferença antes da rodada. | Reusar os 14 casos existentes em duas rodadas, uma após recarga/reinício controlado. Registrar resumo autorizado, fatos esperados, resposta, término, tempos e revisão independente. Conferir especialmente RUL 10 h no caso original, recusa de medidas atuais para leituras antigas, distinção saúde/RUL e explicação de MAE; preservar valores próprios dos holdouts. Manter oráculo SQL em banco descartável se adaptar o avaliador existente. | 14/14 completos e factualmente aprovados em cada rodada. Falta de resposta reprova disponibilidade, não prova alucinação. Uma falha factual encerra adoção do 1B, mesmo que Metal seja rápido; não selecionar só as perguntas fáceis nem trocar modelo automaticamente. |
| **6. Integração — pendente** | Marco A aprovado, diferença de execução aceita pelo professor e escolha explícita do usuário de integrar. | Implementar adaptador mínimo, seleção comum e overlay alternativo; TDD de lifecycle/coordenação, integração PostgreSQL e HTTP/SSE/navegador. Repetir baseline com pilha completa sem LLM e os 14 casos com o perfil integrado. Só então ensaio real autorizado da pilha com jobs representativos em recursos descartáveis. | Exclusão e recuperação comprovadas, métricas da pilha completa dentro dos critérios, apps utilizáveis, dados pessoais intactos e conformidade registrada. Sem aceitação escolar, manter como experimento isolado. Se falhar, reverter; aprovação isolada permanece limitada. |
| **7. Decisão/reversão — pendente** | Evidências dos dois marcos e conformidade revisadas. | Registrar resultados separados de desempenho, memória e factualidade, decisão, limites e reversão. Comparar alternativas somente como propostas futuras; todos os computadores conhecidos do grupo têm 8 GB. Liberação pessoal exige escolha do usuário. | Adotar apenas perfil qualificado e aceito para o trabalho. Se falhar qualidade ou memória, encerrar a rodada e pedir escolha de novo cenário/candidato, sem iniciar 3B ou outro modelo nem presumir máquina maior disponível. |

## Critérios a congelar antes da execução

São propostas de aceite, não resultados nem garantias. Valores derivados da
baseline devem ser escritos no relatório **antes** de carregar o candidato.
Alterar um critério cria nova rodada e preserva a reprovação anterior.

| Dimensão | Regra e justificativa |
| --- | --- |
| Condições | Bateria e apps habituais abertos; registrar carga inicial/final e modo de economia, sem alterá-lo. Interromper se houver alerta de bateria baixa, suspensão ou troca de alimentação: não misturar condições. |
| Interrupção de memória | Parar admissão de chamadas ao primeiro OOM, pressão crítica ou travamento perceptível; pressão de aviso por 60 s também interrompe. A janela evita tratar um pico isolado como falha sustentada. Executar cleanup e confirmar descarga; não encerrar apps pessoais. |
| Estabilidade | Baseline deve terminar com pressão normal e operações de uso responsivas. Não aceitar crescimento sustentado de alocação viva ou swap entre ciclos. Após descarga, medir 2 min, verificar memória do motor liberada e taxas de paginação estabilizadas, comparando com a baseline. Não exigir retorno imediato do total de swap ao valor inicial; distinguir páginas antigas em swap e cache recuperável de alocação viva do motor. |
| Paginação | Registrar taxas em MiB/s e crescimento de swap. Limite comparativo: p95 de swap-out nas janelas estáveis não deve superar p95 da baseline além da resolução da coleta; publicar essa resolução e ambos os valores. Baseline com pressão/travamento não legitima paginação alta. |
| Tempo aquecido | Meta de primeiro texto ≤10 s e conclusão ≤60 s por caso, escolhidas para interação/apresentação; teto existente de geração 90 s. Publicar todos os tempos, mediana e pior caso; não alegar SLA com amostra pequena. |
| Carga fria/cleanup | Medir separadamente; não superar teto atual de preload 300 s. Cancelamento encerra entrega e tenta cleanup por até 12 s; incerteza mantém bloqueio. O teto de 300 s não é meta de experiência. |
| Contexto | Inicialmente 1.024 tokens, saída 256, temperatura 0 e prompt atual. Verificar orçamento de instruções + template + resumo + pergunta + saída. Se não couber, registrar falha de configuração; nunca truncar fatos silenciosamente. |
| Qualidade/disponibilidade | Duas rodadas 14/14 completas e aprovadas. Zero número inventado, confusão MAE/RUL, leitura antiga apresentada como atual, vazamento ou atuação alegada. Palavras corretas e fluxo concluído não bastam. |
| Benefício de Metal | Publicar ganho ou ausência de ganho em velocidade e consumo, separado do aceite factual. Não exigir nem anunciar multiplicador de speedup com base na mediana histórica. Nenhuma vantagem observada justifica integrar um 1B factualmente reprovado. |
| Conformidade escolar | Antes da integração/adoção, registrar aceitação explícita para motor nativo fora de container no Mac. Modelo capaz de CPU, localidade e ligação HTTP com Compose não demonstram, sozinhos, o requisito de LLM em container. |
| Coordenação final | Zero sobreposição entre execução pesada dos jobs e carga/inferência do LLM. Recuperação normal de cancelamento/descarga automática; falha ambígua pode exigir intervenção segura, nunca liberação presumida. |

## Contratos e exclusão segura para o marco B

Reutilizar [llm.py](../../backend/app/services/llm.py),
[assistant.py](../../backend/app/services/assistant.py) e
[jobs.py](../../backend/app/services/jobs.py): `HEAVY_JOB_LOCK`, `LOADING_LOCK`
e `llm_memory_guard`. O lock evita concorrência enquanto a sessão vive; o
marcador conserva a incerteza após uma queda.

1. Antes de qualquer carga/inferência, adquirir lock, verificar jobs `running`
   e marcador, persistir barreira antes do HTTP. Status deve ser passivo.
2. Durante inferência, manter sessão original e revalidar autorização. Somente
   término válido e request encerrado permitem remover a barreira nessa sessão.
3. Antes do job, impedir novas inferências, descarregar e confirmar quiescência
   (nenhuma carga/inferência ainda ativa); só então iniciar seu executor.
4. Falha/cancelamento/timeout fecha stream e tenta descarga. HTTP 200/202,
   socket fechado, contagem de unload ou listas vazias isoladas não comprovam
   encerramento de uma carga atrasada. Conservar marcador se houver dúvida.
5. Perda SQL, queda da API/coordenador ou reinício DMR não limpam marcador por
   TTL. Recuperação impede novos pedidos, encerra atores antigos, comprova
   parada/reinício do motor e reconcilia sob lock. Sessão antiga não limpa estado novo.
6. Job falho/cancelado só libera espaço após executor/subprocesso terminar.
   Job órfão `running` bloqueia recarga até reconciliação segura.

DMR é acessível sem autenticação própria. JWT, dono, rate limit e SSE continuam
na API ColdSafe; não encaminhar JWT ao motor, abrir endpoint no navegador ou
aceitar URL arbitrária. Manter limites de resposta, rejeição de redirects e
proxies herdados. Conferir acesso/retenção de prompts antes de usar dados pessoais.

O lock SQL só controla participantes ColdSafe. Exigir uso dedicado verificável
do runtime no ensaio; outro modelo/cliente bloqueia o teste, não autoriza
descarregá-lo. Se precisar compartilhar runtime, uma barreira efetiva de acesso
será pré-requisito adicional; convenção de uso não é isolamento contra qualquer
processo. Não montar socket Docker nem permitir preload automático do Compose
fora do coordenador. Não executar Ollama e DMR simultaneamente para comparação.

## Escopo mínimo de integração, condicional e ainda não implementado

Esta tabela só será executável após marco A, conformidade e escolha da etapa 6.
Os clientes descartáveis das etapas 3–5 não autorizam mudar o provedor pessoal
nem implementar antecipadamente o adaptador de produção.

| Arquivos/superfície | Alteração futura |
| --- | --- |
| `backend/app/config/settings.py`, `backend/app/services/llm.py`; novo `backend/app/services/model_runner.py` | Seleção central de dois provedores, destino validado, modelo/digest e lifecycle DMR. Sem framework genérico. |
| `backend/app/services/assistant_transport.py`, `assistant.py`, `jobs.py` | Parser SSE DMR, término/truncamento/cancelamento e uso do mesmo cliente/barreira por todos os participantes. Coordenador em `llm_worker.py` deve usar essa seleção, alterando o arquivo só se necessário. |
| `backend/app/services/assistant_context.py` | Corrigir fato fixo “Ollama em CPU” para o perfil efetivo; preservar resumo privado e seleção de dados. |
| Novo `compose.model-runner.yaml` | Alternativo a `compose.ollama.yaml`, sem iniciar Ollama e sem auto-preload; configuração coerente em backend, geração, treino e coordenador. |
| `scripts/evaluate_assistant.py`, `scripts/benchmark_assistant.py` | Adaptar infraestrutura/medição e rubrica de arquitetura; preservar casos, oráculo SQL e proteção de banco descartável. Replay de JSON histórico sozinho seria só teste do motor, não avaliação nova de SQL/API. |
| Testes existentes de LLM, transporte, coordenação, API e browser | Cobrir perfil DMR e conservar regressão Ollama. Frontend mantém SSE ColdSafe `delta/done/error`, abort e texto parcial incompleto. |
| Configuração, contratos, runbook, versões e apresentação | Atualizar somente após implementação/evidência correspondente; preservar relatos antigos. |

Dependências nesta entrega: **nenhuma**. Para execução futura: pesos exatos no
armazenamento DMR para o perfil 1B verificado e backend identificado; não prever
SDK OpenAI nem biblioteca Python/Node nova. Reusar HTTPX instalado. Espaço do download, temporários, cache
e swap precisa caber sem remover artefatos pessoais.

## Testes planejados e revisão factual

- Unitários: SSE fragmentado/UTF-8, terminal ausente, truncamento, erro, limites,
  identidade errada, destino inválido e status sem efeitos colaterais.
- Integração com PostgreSQL descartável: pergunta/job concorrentes, revogação,
  perda SQL, cancelamento antes do primeiro token, carga atrasada, descarga
  ambígua, job órfão e reinício em cada fase. Testar que o executor não iniciou,
  além de conferir o estado retornado. Testes reais de lifecycle após controlados.
- HTTP/navegador: JWT, cinco admissões/minuto/conta, isolamento por dono,
  desconexão, cancelamento e eventos `delta/done/error`; nunca sucesso em parcial.
- Os [14 casos](../../scripts/evaluate_assistant.py) são seis originais (estado,
  menor saúde, RUL, alerta, métricas, arquitetura), sem dados, dados antigos e
  seis holdouts. Preservar a diferença entre menor saúde e menor RUL no holdout.
  Revisão por sujeito/valor/unidade/atualidade/limitação, independente do executor.
- Na implementação, testes focados e cobertura dos módulos alterados ≥80%,
  sem confundir cobertura com aprovação factual ou cobertura global do projeto.

## Alternativas, reversão e decisão

| Alternativa | Custo e regra de escolha |
| --- | --- |
| DMR/Metal com 1B | Escolha atual de investigação; backend antes observado disponível, com adaptação de lifecycle/API ainda pendente. Adotar somente após os dois marcos e aceitação da diferença de execução pelo professor. Ganho de velocidade não corrige reprovação factual. |
| Ollama nativo/Metal | Menor distância de API, mas exige instalação/configuração futura, acesso seguro ao host e aceitação explícita da execução nativa fora de container. Mesma disputa de 8 GB; não é solução automática para falta de memória. Alternativa futura, sem instalação autorizada nesta revisão. |
| Outro computador do grupo | Todos os conhecidos têm 8 GB; trocar Windows/Mac não comprova mais margem de memória. Outro cenário ou execução distribuída exige escolha e verificação de conformidade; não presumir máquina maior disponível ou dividir a pilha automaticamente. |

Antes de reverter: suspender admissões, encerrar fluxos/cargas, confirmar descarga
ou recuperar ambiguidade; só então trocar provedor/overlay. Preservar alterações
locais anteriores, pesos Ollama, volumes e modelos preditivos. Não usar reset
global, limpeza de volumes ou apagar marcador para contornar falha. Conferir IDs
e artefatos antes/depois sem exportar conteúdo pessoal. Voltar ao CPU restaura
configuração, não viabilidade; reversão pode terminar com assistente indisponível.

## Fontes verificadas na investigação

- [DMR: Metal e llama.cpp](https://docs.docker.com/ai/model-runner/inference-engines/).
- [DMR: execução nativa e API sem autenticação](https://docs.docker.com/ai/model-runner/).
- [API e formatos](https://docs.docker.com/ai/model-runner/api-reference/).
- Código oficial [Ollama compatível v1.1.1](https://github.com/docker/model-runner/blob/v1.1.1/pkg/ollama/http_handler.go): prontidão não fornece os mesmos campos; generate vazio/descarga retornam `{}`, diferentes das confirmações exigidas atualmente.
- [Scheduler v1.1.1](https://github.com/docker/model-runner/blob/v1.1.1/pkg/inference/scheduling/http_handler.go): configure retorna 202 com preload em background; unload não interrompe requisição ativa. Revalidar se a versão mudar.
- [Ollama: Metal](https://docs.ollama.com/gpu) e [restrição de GPU no container macOS](https://docs.ollama.com/faq#how-do-i-use-ollama-with-gpu-acceleration-in-docker).

## Pesquisa complementar — modelos menores em CPU (04/11)

Após a baseline interrompida, o usuário escolheu pesquisar candidatos menores
na internet. [Pesquisa e metadados](../evidence/small-model-research-2026-11-04/README.md)
indicam Qwen3-0.6B Q8 oficial (639 MB) para primeiro ensaio e Granite Nano 350M
Q8 oficial (378 MB) como reserva de menor peso; nenhum está qualificado no Mac.
Tamanho de arquivo não é RAM total. A pesquisa prioriza CPU em container para
atender ao enunciado; DMR/Metal nativo no Mac não satisfaz literalmente essa
exigência sem aceitação explícita do professor. A pesquisa é referência
preservada; a escolha posterior neste roadmap é investigar **Llama 3.2 1B
DMR/Metal**, sem adotar Qwen/Granite nem autorizar integração.

Nenhum download, carga, mudança de runtime/configuração ou ensaio foi executado
na pesquisa. Baseline continua não aprovada; etapas 2–7 não avançaram.
A sugestão de ensaio CPU desse relatório não é mais a próxima escolha deste
roadmap. Retomar o 1B/Metal começa por condições válidas de memória; preservar
as duas baselines e os critérios, sem reescrever a pesquisa histórica.

## Checkpoint documental

- **Planejamento anterior:** roadmap e ligação no registro da apresentação;
  55 links locais e whitespace conferidos naquela entrega, com revisão
  documental independente. Isso permanece evidência antiga, sem ensaio Metal.
- **Adaptação atual em 04/11/2026:** candidato principal alterado de 3B para
  Llama 3.2 1B Instruct Q4_K_M no DMR/Metal, com identidade ainda pendente.
  Tempos CPU recalculados do JSON histórico e reprovação factual preservada.
  Objetivos de desempenho, memória e qualidade separados; conformidade escolar
  explícita antes da integração/adoção. Somente este roadmap foi editado;
  nenhum arquivo criado e nenhuma dependência adicionada. Conferidos 17 links
  locais, tempos históricos, whitespace/diff e hashes de 17 arquivos anteriores.
  Revisão independente incorporada, incluindo a distinção entre aceleração GPU
  e execução fora de container. Nenhum ensaio operacional.
- **Etapa 1, primeira tentativa em 04/11/2026:** pré-checagem/inventário executados, sem mudança
  operacional. Bateria 10% com aviso Early impediu iniciar os 900 s; às 15:45:19
  inventário informou AC conectado/12%. `lowpowermode 0` conservado. Pressão
  bruta 2 nas observações, sem prova de persistência por 60 s. Todos os 16
  containers parados; DMR em execução com listas vazias. VM anunciou 5,7856 GiB
  de capacidade, não consumo. Swap e disco registrados como estoques no
  [relatório](../evidence/assistant-metal-baseline-2026-11-04/README.md) e
  [JSON](../evidence/assistant-metal-baseline-2026-11-04/preflight.json).
- **Etapa 1, segunda tentativa em 04/11/2026:** coleta entre 16:08:59 e 16:09:59,
  13 pontos/12 intervalos, interrompida após 60,0049 s de aviso (`2`) em todos os
  pontos. Battery Power/40% sem alerta; `lowpowermode 0` conservado. Swap-out
  medido zero e estoque de swap diminuiu `48.00M`; isso não anula pressão.
  Taxas/resolução/p95 publicados apenas para o trecho interrompido, sem limiar
  válido para candidato. [Relatório](../evidence/assistant-metal-baseline-2026-11-04-r2/README.md)
  e [resumo](../evidence/assistant-metal-baseline-2026-11-04-r2/summary.json).
- **Verificações da repetição:** autochecks do coletor, JSON, taxas por deltas,
  auditoria de timestamps de parede contra monotônico, configurações/evidência
  anterior por hash e metadados antes/depois. Nenhuma dependência adicionada;
  sem mudanças operacionais ou em dados/modelos pelo agente. Revisão do coletor
  apontou limite de suspensão, documentado e auditado nesta rodada.
- **Limites:** baseline não aprovada; sem 15 min completos, responsividade
  aprovada, consumo instantâneo da VM ou ensaio do candidato. Não há causa
  demonstrada por app, GPU ou energia. Primeira tentativa e segunda não são
  agregadas; critérios preservados. Etapas futuras replanejadas para o 1B,
  sem aprovação ou execução antecipada.
- **Próxima ação:** aguardar escolha de executar nova etapa 1 para o ensaio
  1B/Metal, nas mesmas condições: 15 min/5 s sem modelo, responsividade e
  detecção de suspensão corrigida no novo coletor, preservando o instrumento
  antigo. Não fechar apps nem alterar energia/RAM para aprovar. Se a baseline
  falhar, parar. Etapa 2 não iniciada; não importar/baixar pesos antes dela.
  Na retomada, ler este arquivo e a evidência da segunda tentativa; consultar
  a evidência CPU 1B somente quando necessária à comparação.
