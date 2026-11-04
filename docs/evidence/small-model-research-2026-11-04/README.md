# Pesquisa — assistente menor em CPU para o ColdSafe

**Data:** 04/11/2026, America/Sao_Paulo. **Estado:** pesquisa concluída;
nenhum candidato qualificado ou carregado. **Indicação para primeiro ensaio:**
Qwen3-0.6B, GGUF Q8_0 oficial da Qwen, sem thinking. **Reserva de menor peso:**
Granite 4.0 Nano 350M, GGUF Q8_0 oficial da IBM. A ordem é uma decisão de
investigação, não resultado comparativo medido no ColdSafe.

## Pergunta e restrições

Encontrar candidato menor que Llama 3.2 3B para Mac M1/8 GiB, fora da tomada,
com aplicativos pessoais abertos, CPU em container no Compose, português e
respostas fiéis ao resumo preparado pelo backend. Sem nuvem, instalação,
download de pesos, carga, inferência, geração, treinamento ou mudança operacional.

As perguntas de pesquisa foram: quais modelos pequenos incluem português;
quais artefatos/quantizações realmente estão disponíveis; o que seus tamanhos
permitem inferir sobre RAM; quais diferenças de runtime/template importam;
quais candidatos repetiriam reprovações já conhecidas.

A [segunda baseline](../assistant-metal-baseline-2026-11-04-r2/README.md)
continua não aprovada: 13 pontos em 60 segundos com aviso de pressão. Esta
pesquisa não a substitui e não autoriza carregar modelo nesse estado.

O [requisito local R15](../../aiot/requirements.md) exige LLM CPU no Compose;
o enunciado fornecido pelo usuário apresenta 3B como exemplo, não tamanho
obrigatório. DMR/Metal no Mac executa o motor fora de container, segundo a
[documentação Docker](https://docs.docker.com/ai/model-runner/#execution-environment).
Por isso, esta shortlist prioriza Ollama/CPU em container e não aprova a
integração Metal planejada no [roadmap](../../aiot/assistant-metal-roadmap.md).

## Shortlist e decisão

**MB/GB abaixo são decimais e representam arquivos ou camadas, não RAM medida.**
Os [metadados públicos retidos](metadata.json) contêm bytes, fontes e hashes
declarados pelos distribuidores. Nenhum arquivo de pesos foi solicitado.

| Prioridade | Candidato/artefato exato | Peso verificado | Motivo e limite |
| --- | --- | ---: | --- |
| 1 | `Qwen/Qwen3-0.6B-GGUF` / `Qwen3-0.6B-Q8_0.gguf` | 639.446.688 bytes, 639,45 MB | Artefato do autor, modelo pós-treinado, português declarado pela família e menor peso que o 3B; Q8 evita começar com quantização mais agressiva. Não há avaliação ColdSafe. |
| 2 | `ibm-granite/granite-4.0-350m-GGUF` / `granite-4.0-350m-Q8_0.gguf` | 378.138.016 bytes, 378,14 MB | Instruct, português explícito, maior redução de peso. A escala de 350M torna a fidelidade factual uma dúvida importante; não afirmar que acertará 14 casos. |
| Reserva | `ggml-org/Qwen3.5-0.8B-GGUF` / `Qwen3.5-0.8B-Q8_0.gguf` | 833.592.096 bytes, 833,59 MB | Conversão da equipe llama.cpp para modelo mais recente; arquitetura/pacote multimodal exigem mais cuidado. Não confundir esse arquivo com a tag Ollama. |
| Se houver margem e faltar qualidade | `ibm-granite/granite-4.0-1b-GGUF` / `granite-4.0-1b-Q4_K_M.gguf` | 1.023.645.440 bytes, 1,024 GB | Instruct multilíngue, mas o nome “1B” corresponde a cerca de 1,6B na tabela oficial. Mais pesado; não é primeira opção para reduzir ao máximo. |

Fontes dos artefatos: [Qwen 0.6B Q8](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/blob/main/Qwen3-0.6B-Q8_0.gguf),
[IBM 350M Q8](https://huggingface.co/ibm-granite/granite-4.0-350m-GGUF/blob/main/granite-4.0-350m-Q8_0.gguf),
[ggml-org 0.8B Q8](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/blob/main/Qwen3.5-0.8B-Q8_0.gguf),
[IBM “1B” Q4](https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF/blob/main/granite-4.0-1b-Q4_K_M.gguf).
Português Qwen: [lista dos 119 idiomas](https://qwenlm.github.io/blog/qwen3/).
Português, pós-treino e limitações Granite: [card 350M](https://huggingface.co/ibm-granite/granite-4.0-350m).
Parâmetros reais: [tabela IBM](https://huggingface.co/ibm-granite/granite-4.0-1b).
Os dois candidatos principais são publicados sob Apache 2.0, conforme os cards
dos autores: [Qwen3](https://huggingface.co/Qwen/Qwen3-0.6B) e IBM acima.

Q8 significa representação quantizada de maior precisão que Q4; não significa
que um modelo de 350M/0.6B adquira a capacidade de um 3B. Selecionar Q8 aqui
preserva mais precisão dos pesos enquanto ainda reduz tamanho. Não há evidência
de que a quantização tenha sido a causa das reprovações anteriores.

O Qwen3-1.7B sem thinking é outra reserva de capacidade: a camada
`qwen3:1.7b-q4_K_M` tem **1.359.279.776 bytes**, cerca de 1,36 GB, conforme seu
[manifest público](https://registry.ollama.ai/v2/library/qwen3/manifests/1.7b-q4_K_M).
Não é Qwen2.5-1.5B. Não o priorizei para o menor orçamento. Na comparação
publicada pela Qwen, o 1.7B supera Qwen3.5-0.8B em IFEval/MMMLU non-thinking;
isso não mede o ColdSafe nem autoriza comparar diretamente com tabelas IBM de
outro protocolo. [Resultados da Qwen](https://huggingface.co/Qwen/Qwen3.5-0.8B#benchmark-results).

## Armadilhas que a pesquisa encontrou

- **Artefatos Qwen diferentes:** a tag Ollama `qwen3:0.6b-q4_K_M` tem camada de
  522.640.096 bytes; `qwen3:0.6b-q8_0` tem 832.278.240 bytes. O Q8 oficial Qwen
  da shortlist tem 639.446.688 bytes e outro hash. São distribuições distintas;
  não usar o tamanho de uma para prometer o download/consumo de outra. A página
  Ollama também imprime 752M, enquanto o autor chama a família de 0.6B; essa
  diferença de contagem/empacotamento não foi reconciliada. A seleção é pelo
  arquivo oficial identificado, não pela equivalência presumida das tags.
  [Tag Q4](https://ollama.com/library/qwen3:0.6b), [manifest Q8](https://registry.ollama.ai/v2/library/qwen3/manifests/0.6b-q8_0).
- **Tags Granite genéricas:** `granite4:350m` está em BF16, camada de
  708.439.456 bytes; `granite4:1b` está em BF16, camada de 3.267.401.472 bytes.
  Elas não são os GGUF quantizados da shortlist. O mesmo nome da família não
  garante o mesmo peso. [Tags oficiais](https://ollama.com/library/granite4/tags).
- **Qwen3.5 no Ollama:** `0.8b-q8_0` inclui modelo de 811.843.520 bytes e
  projetor de imagem de 207.346.304 bytes; soma das camadas com metadados:
  1.019.201.245 bytes. A tag genérica `0.8b` anuncia ainda mais componentes
  MTP/draft. Isso não equivale a consumir toda essa soma em RAM durante texto,
  mas impede vender esse pacote como um download de “0,5 GB”. Não se mediu
  residência de projetor/draft. [Tags](https://ollama.com/library/qwen3.5/tags),
  [manifest explícito](https://registry.ollama.ai/v2/library/qwen3.5/manifests/0.8b-q8_0).
- **Contexto máximo não é configuração para o Mac:** limites nativos de dezenas
  ou centenas de milhares de tokens não devem ser usados automaticamente.
  Manter o orçamento inicial de 1.024; verificar tokenizer/template + instruções
  + resumo + pergunta + 256 de saída. Se não couber, reprovar configuração e
  discutir revisão explícita, sem apagar fatos ou elevar limites silenciosamente.

## Quanto de RAM isso pode significar

Não encontrei evidência primária que comprove RAM, latência e fidelidade desses
artefatos com **esta pilha, este M1, bateria e aplicativos pessoais**. Relatos
de “8 GB” frequentemente se referem a VRAM dedicada ou a um modelo isolado.
Não foram usados como garantia de capacidade do Mac inteiro.

Há uma conta parcial verificável para Qwen3-0.6B oficial. Seu
[config do autor](https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json)
declara 28 camadas, 8 heads KV e `head_dim=128`. Com contexto 1.024, uma
requisição e K/V em FP16, `2 × 28 × 8 × 128 × 1024 × 2` dá **112 MiB de KV**.
O arquivo Q8 corresponde a **609,82 MiB**; pesos + esse cache somam
**721,82 MiB**, aproximadamente 0,705 GiB. É uma **estimativa parcial**,
excluindo buffers, alocações do motor/Ollama, outros caches, VM, sistema e apps.
Não é uma previsão do RSS nem teto de uso. `head_dim` explícito foi usado;
não se presumiu `hidden_size/num_attention_heads`.

O [FAQ Ollama](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests)
explica que contexto e paralelismo ampliam memória. O Compose já fixa uma
requisição/modelo e contexto 1.024; não se alterou isso. A capacidade anunciada
da VM e o limite Ollama de 3.328 MiB não foram tratados como consumo ou espaço
livre. Não há um valor total de RAM qualificado para nenhum candidato.

**Inferência da pesquisa:** os arquivos de 378/639 MB são alternativas concretas
para reduzir pesos em relação ao 3B. **Não demonstrado:** que essa economia
elimine o aviso existente ou deixe espaço para todos os serviços. Zero chamada
real foi realizada nesta investigação.

## Compatibilidade e esforço mínimo futuro

O [Compose local](../../../compose.ollama.yaml) fixa Ollama **0.40.3**, não
0.4.3; a [release existe](https://github.com/ollama/ollama/releases/tag/v0.40.3).
Foi consultada a árvore pública dessa tag, que contém parsers Qwen3/Qwen3.5;
isso não substitui teste de importação, template ou carga de cada GGUF.
Compatibilidade efetiva com a imagem Linux/ARM64 do projeto continua pendente.
Não se propõe atualizar o runtime automaticamente.

Qwen3 oferece um hard switch para desativar thinking, além de `/no_think`
como instrução de prompt; não são mecanismos equivalentes. O
[card Qwen](https://huggingface.co/Qwen/Qwen3-0.6B#switching-between-thinking-and-non-thinking-mode)
e a [API Ollama](https://docs.ollama.com/capabilities/thinking) documentam o
controle. A requisição atual em
[assistant_transport.py](../../../backend/app/services/assistant_transport.py)
usa `/api/chat`, contexto 1.024, saída 256, temperatura 0 e não envia `think`.
Logo, ensaiar Qwen3 não seria só renomear o modelo: seria necessário confirmar
template, desativação efetiva, conteúdo de streaming e término sem truncamento.
Nada disso foi implementado. O autor recomenda outros parâmetros de amostragem;
isso é diferença a avaliar, não autorização para trocar a temperatura atual.

O resumo pronto do backend é justamente a integração exigida. Não propor RAG,
ferramentas externas, acesso direto do LLM ao banco, fine-tuning ou uma segunda
tradução por LLM para fazer o candidato passar. Modelos saúde/RUL são regressões
separadas: a pesquisa de chat não os substitui nem os toca.

O grafo MCP estava indisponível (`Transport closed`); somente arquivos já
identificados e trechos necessários foram consultados como fallback. Não houve
indexação pesada, leitura de todo o histórico ou execução de comandos antigos.

## Famílias avaliadas e não priorizadas

- **Llama 3.2 1B Q4_K_M e Qwen2.5 1.5B Q4_K_M:** reprovações locais por fatos
  e, no Qwen, disponibilidade, preservadas na
  [apresentação](../../aiot/presentation.md). Qwen3/3.5 são outros candidatos;
  não herdam aprovação ou reprovação automaticamente.
- **Gemma 3 1B IT:** a tabela específica do lançamento diferencia 1B English
  de 4B+ multilíngues. Não assumir que a alegação genérica de 140 idiomas
  qualifica essa versão para português. Não é a primeira escolha linguística.
  [Lançamento técnico HF](https://huggingface.co/blog/gemma3).
- **SmolLM2 360M:** card declara foco em inglês; **SmolLM3 é 3B**, sem a redução
  procurada. [SmolLM2](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct),
  [SmolLM3](https://huggingface.co/HuggingFaceTB/SmolLM3-3B).
- **LFM2.5 1.2B Instruct:** GGUF oficial Q4 tem cerca de 731 MB, mas português
  não está na lista de oito idiomas do autor. Não é primeira escolha para chat
  em português. [Card Liquid](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct).
- **LFM3 1.7B:** lançamento recente, inclui português e GGUF CPU. Porém,
  thinking vem habilitado e sua desativação pode ser inconsistente segundo o
  autor. O suporte Linux/Windows foi anunciado em Ollama 0.40.13, posterior ao
  pin 0.40.3. Adiciona mudança de runtime e risco de consumir o orçamento de
  saída; reserva de pesquisa, não primeira escolha. [Card LFM3](https://huggingface.co/LiquidAI/LFM3-1.7B),
  [release Ollama](https://github.com/ollama/ollama/releases/tag/v0.40.13).
- **Granite MoE ou modelos com “parâmetros ativos”:** não confundir ativos com
  total residente. Granite tiny-h anuncia 1B ativo, mas 7B totais; não é um
  substituto com pesos de 1B. [Família IBM](https://www.ibm.com/granite/docs/models/granite4-0).

## Resultado, verificações e próxima ação

**Confiança alta:** existência dos artefatos, tamanhos/digests declarados e
idiomas explicitamente listados. **Confiança moderada:** prioridade sugerida,
baseada em peso, idioma e esforço de integração. **Confiança insuficiente:**
RAM total, velocidade na bateria, fidelidade ao resumo e estabilidade da pilha.

Foram usadas buscas web, cards dos autores, páginas dos artefatos, manifests,
documentação e releases oficiais; duas investigações independentes apoiaram a
triagem. Firecrawl/Exa não estavam disponíveis; usou-se busca web e leitura das
fontes primárias. Metadados HF/registry foram consultados por JSON sem pesos.
O Python local falhou na cadeia de certificados; a leitura prosseguiu com
`curl` do sistema, **mantendo verificação TLS**, sem instalar ou reconfigurar nada.
Hashes são declarações remotas, não hashes de pesos baixados/verificados localmente.

Verificações executadas: JSON válido; tamanhos/totais das seis distribuições
Ollama e cinco arquivos HF coerentes com o registro; conta parcial do KV
recalculada; 21 links locais e whitespace/diff aprovados. Revisão independente
sem achados materiais. Os hashes de 12 arquivos de configuração, transporte e
evidências anteriores permaneceram iguais durante a escrita. A comparação do
roadmap confirmou somente acréscimo da seção de pesquisa, sem mudar critérios
ou resultados. Não foram executados testes de aplicação ou modelo.

Somente esta pasta (relatório e metadados) e uma referência no roadmap foram
criadas/alteradas. Nenhuma dependência adicionada; nenhum modelo, serviço,
configuração, volume, dataset, modelo preditivo ou credencial alterado.

**Próxima ação proposta:** usuário escolher o Qwen3-0.6B Q8 oficial como
candidato para um ensaio CPU separado. Antes de qualquer carga, recuperar uma
baseline válida nas mesmas condições e definir preparo reversível, identidade,
template/non-thinking, espaço e avaliação. Em seguida, se autorizado, testar
carga/descarga, recursos e os 14 casos em duas rodadas com recursos descartáveis.
Não reduzir o corpus nem tratar resposta curta/rápida como acerto factual.
Pesquisa não inicia download, etapa 2 Metal ou integração automaticamente.
