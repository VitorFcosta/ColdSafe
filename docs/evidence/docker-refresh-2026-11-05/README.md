# Atualização local das imagens Docker — 05/11/2026

Resultado: nove imagens da aplicação reconstruídas a partir do commit
`62cb4cca651a00d74e8b1d627607013637e5ba30` e nove containers recriados,
sem iniciar os serviços da aplicação. Os sete containers de infraestrutura e
preparação permaneceram com suas identidades anteriores. Os 16 estão parados:
nove em `created` e sete em `exited`.

## Escopo e condições observadas

- Mac M1 de 8 GB, fora da tomada: bateria de 41% antes e 40% ao final.
- Pressão de memória do macOS em nível `2` (alerta) antes e depois. A pilha
  já estava parada no início; essa observação não atribui a pressão à pilha.
- Swap ocupado: 3.654,38 MiB antes e 4.566,12 MiB depois. São estoques em dois
  instantes; não foram medidas taxas de paginação nem isolada a causa da variação.
- Capacidade de RAM reportada pelo engine: 6.212.268.032 bytes, sem alteração.
  É capacidade da VM, não consumo atual dos containers nem RAM livre do Mac.
- Aproximadamente 19 GiB livres no volume do projeto. Nenhuma limpeza de imagens,
  caches ou volumes foi executada.
- Aplicativos pessoais permaneceram abertos. Nenhum comando de alteração de
  energia, limites de RAM ou credenciais foi executado. O arquivo de ajustes do
  Docker Desktop não pôde ser lido por proteção do macOS; a capacidade reportada
  pelo engine e os limites dos containers foram comparados antes/depois.

## Operação executada

Construções sequenciais de `backend`, `gateway`, `writer`, `simulator`, `frontend`,
`generation`, `training`, `models` e `llm`, com os overlays atuais de AIoT, jobs,
inferência e Ollama. O cache existente de dependências foi reutilizado.
Não houve atualização de versões, instalação no host ou nova dependência no projeto.

Após validar a composição e simular a recriação, foi usado `docker compose create
--no-build --pull never` para os nove serviços da aplicação. Não foram usados
`up`, `start`, `run`, `down -v`, remoção de volumes ou preparação de pesos.

O runtime continua com a integração Ollama existente. Esta operação não implementa
Metal/Model Runner, não troca o modelo e não avança o roadmap do assistente.

## Verificações executadas

- Nove construções concluídas com código de saída zero; verificação TypeScript
  e build de produção do frontend aprovados durante a construção.
- 483 comparações SHA-256 de arquivos de código copiados dos oito containers
  Python contra os arquivos versionados: nenhuma diferença. Os arquivos podem
  se repetir entre serviços; não são 483 arquivos únicos do repositório.
- Quatro recursos referenciados pelo HTML do frontend existem e têm os nomes
  produzidos neste build. Configuração Nginx idêntica ao projeto; quatro recursos
  da documentação Swagger offline presentes. Hashes e tamanhos em `state.json`.
- Os nove containers da aplicação apontam para as imagens recém-construídas.
- Mesmo conjunto de 16 serviços, mesmas montagens (comparadas pelo destino),
  mesmas permissões e mesmos limites de RAM/CPU/configuração Compose.
- Mesmo conjunto de 222 volumes locais do engine, com nomes e metadados de
  criação preservados. Esse total inclui volumes alheios à pilha pessoal;
  não equivale à quantidade de volumes do ColdSafe em uso.
- `.env` e os dois arquivos presentes em `simulator/local` mantiveram seus hashes.
  Seus conteúdos não foram incluídos nesta evidência.
- Consulta de eventos do projeto entre as capturas: zero eventos de início de
  containers. Nenhuma inferência, geração, treino ou carga de modelo executada.

Essas verificações comprovam a atualização das imagens/containers e a preservação
das identidades/montagens. Não são um backup nem uma comparação byte a byte dos
conteúdos dos bancos, datasets e modelos nos volumes. Os serviços que escrevem
nesses volumes permaneceram parados.

## Avaliação de otimização e próxima ação

A composição completa possui 14 serviços persistentes e dois preparadores de
brokers; `ollama-prepare` é uma preparação adicional opcional, não criada nesta
operação. Separar serviços preserva isolamento e os requisitos de mensageria,
bancos e consumidores distintos de `docs/aiot/requirements.md`.

Recomendação ainda não implementada: preparar uma composição de uso diário para
monitoramento/gêmeo/previsões com dez serviços persistentes, deixando geração,
treino e assistente para os respectivos usos. Docker Compose permite seleção por
[perfis](https://docs.docker.com/compose/how-tos/profiles/), mas essa composição
precisa ser validada: os jobs do overlay atual também dependem da coordenação de
descarga/locks do Ollama. Parar Ollama arbitrariamente pode impedir os jobs.

Não há consumo por serviço medido nesta operação, pois eles ficaram parados.
Não foi feita nova baseline de 15 minutos nem validação em Windows. Nenhuma
economia de RAM ou latência pode ser quantificada a partir desta atualização.
O limite de 3,25 GiB do Ollama e o de 1 GiB do treino são tetos, não consumo medido.

Próxima ação depende da escolha do usuário: preparar o modo de uso diário ou
retomar a etapa escolhida do roadmap. A partida e o ensaio funcional completo
continuam pendentes; a pressão de memória atual exige atenção antes de ligar tudo.

`state.json` conserva metadados e verificações. O log bruto de construções e
recriação foi arquivado fora do repositório. Nenhum código, Compose, requisito
ou roadmap foi alterado naquele ensaio.
