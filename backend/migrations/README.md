# Migrações PostgreSQL

`initialize_schema()` em `app/repositories/postgres.py` aplica somente versões
ausentes de `schema_migrations`, em uma transação protegida por advisory lock.
O backend chama esse runner durante a inicialização. Não executar os arquivos SQL
manualmente em sequência em uma base já migrada: o ledger evita repetição.

## B2-05: versões 004 e 005

- 004 acrescenta `users.role`: `viewer`, `operator`, `admin`. Contas existentes
  e cadastros normais recebem `operator`, preservando a capacidade atual de
  administrar seus ambientes. Cadastro público rejeita `role`; promoção exige
  operação administrativa confiável. Não promover automaticamente a primeira
  conta. A B2-06 implementa a autorização por papel e administração auditada.
- 005 acrescenta `datasets`, `jobs`, `models`, `model_activations`, `active_models`.
  Não altera senhas, sessões, dispositivos, regras, alertas, comandos ou auditoria.
  Telemetria e histórico do InfluxDB não são tocados.

| Registro | Propriedade e vínculo |
| --- | --- |
| Dataset | Dono obrigatório; job de geração de origem opcional para dados importados; dados offline ficam fora do PostgreSQL |
| Job | Dono obrigatório; ambiente opcional e dataset de treino do mesmo dono |
| Modelo | Pacote saúde + RUL; dataset e job de treino compatíveis do mesmo dono |
| Ativação | Dono; modelo solicitado e anterior do mesmo dono; uma pendente por dono |
| Modelo ativo | Uma referência por dono; contas diferentes podem usar versões próprias |

As FKs incluem o proprietário, recusando referências cruzadas mesmo por UUID
válido. `AiotRepository` filtra todas as leituras pelo proprietário recebido da
autenticação; papel `admin` não dá acesso aos dados de outra conta. Não há RLS:
a credencial SQL de serviço é confiável e pode ler todas as contas. Nunca
entregar essa credencial ao navegador nem usar dono enviado pelo cliente como
autorização. As futuras APIs/workers devem usar sessão + propriedade.

Job de geração tem dataset de entrada nulo; treino tem dataset e duas unidades
(as duas regressões). Contadores/estado/erro/resultados têm constraints. Resultado
concluído aponta para dataset ou modelo persistido do mesmo dono e produzido
pelo próprio job, por FK composta com o ID do job de origem. Dataset importado
sem origem pode ser entrada de treino, mas não resultado de geração. O evento v3
usa `result_id`, derivado de `result_dataset_id` ou `result_model_id` conforme o
tipo. As colunas distintas permitem FKs para ambos os tipos de resultado.

`model_version` é único por proprietário. Modelo referencia o dataset do próprio
job de treino. Versão/layout de features, aprovação de métricas, conteúdo do
artefato, transições de estado, aprovação do dataset e carga/troca do pacote
serão verificados pelos serviços das tarefas B2-17–25; inserir metadados não
significa treinar ou carregar um modelo. `active_models` registra a referência,
sem carregar artefatos. `model_activations.previous_model_id` conserva o anterior.

`artifact_key` é uma chave relativa interna, limitada e sem URL, caminho absoluto,
segmento `..` ou `//`. Não é caminho público nem autorização para desserializar.
Configuração e métricas são objetos JSON; sua validação de negócio pertence aos
serviços futuros. Labels de treino não são acrescentados à telemetria ao vivo.

## Aplicação e recuperação

1. Antes de migrar base importante, parar escritas e gerar backup com `pg_dump`
   em formato custom (`-Fc`), usando a credencial por ambiente/arquivo privado.
   Guardar fora do Git e verificar a restauração em um banco descartável.
2. Com as variáveis habituais do backend configuradas, executar o runner:

   ```sh
   python -c 'from backend.app.config.settings import RuntimeSettings; from backend.app.repositories.postgres import initialize_schema; initialize_schema(RuntimeSettings())'
   ```

3. Conferir `SELECT version FROM schema_migrations ORDER BY version` (1–9).
   Repetir o runner é seguro. Se falhar, toda a rodada de migrações pendentes
   volta ao estado anterior; corrigir a causa e tentar novamente. A versão 003
   continua recusando regras legadas conflitantes.
4. Para recuperar um backup, restaurar **em outro banco vazio**, com `pg_restore
   --exit-on-error --no-owner --no-privileges -d <banco_de_recuperacao> <backup>`;
   conferir dados e apontar a configuração para esse banco após avaliação.
   Não apagar tabelas novas nem o ledger como tentativa de downgrade. Backup
   anterior à migração não contém jobs/modelos criados depois; conservá-los antes
   de decidir recuperar a base antiga.

A versão 006 preserva hashes e sessões anteriores, marcando estas como
`opaque`. Sua aceitação é limitada a 24 horas após `schema_migrations.applied_at`
da versão 6 e à expiração/revogação própria; novas sessões são `jwt`.
`login_rate_limits` persiste contadores por email/IP hasheados e
`websocket_tickets` guarda somente hashes, prazo e consumo. O banco exige
prazo máximo de 60 segundos; o serviço limita também à expiração da sessão.

## Verificação reproduzível

A versão 010 da B2-25 acrescenta `inference_events`, com histórico aceito,
previsão canônica e marcação de confirmação. Fonte/saída são gravadas juntas,
deduplicadas pelo UUID da telemetria. Índices limitam consulta à janela por
proprietário/dispositivo/equipamento e às saídas pendentes. Migração aditiva,
sem alterar telemetria, buckets ou versões de modelos existentes. Retenção
continua sem expurgo automático: apagar a linha elimina histórico/deduplicação
e pode transformar redelivery em novo cálculo; preservar pendências e identidades.

A versão 009 da B2-24 acrescenta `model_outbox`. Solicitação de ativação e
transições de carga gravam evento junto ao efeito PostgreSQL; `sequence` preserva
ordem de publicação e `event_id` identifica redelivery. Cada ativação tem uma
solicitação canônica `api`; `inference` pode publicar seus estados sucessivos.
`published_at` só recebe valor após publisher confirm. Não remove registros nem
altera modelos existentes. Retenção continua manual; não apagar eventos pendentes.

A versão 008 da B2-17 acrescenta `job_outbox`, separada da outbox por dispositivo.
Cada solicitação tem um evento estável por job; mudanças de estado e progresso
gravam seus eventos na mesma transação. `published_at` só é preenchido após
confirmação AMQP. Falha entre confirmação e gravação permite redelivery, tratado
sem reabrir job terminal. Não altera registros existentes nem remove eventos.
A retenção/limpeza da outbox ainda é manual; não apagar solicitações de jobs ativos.
O serviço aplica transições e valida artefato interno não vazio, dono e origem
antes de concluir; as constraints 005 continuam vigentes. Não é prova de qualidade
de dataset/modelo, que pertence às tarefas de geração e treino.

A versão 007 da B2-13 acrescenta inbox, eventos, comandos, alertas, freshness e
outbox `aiot_*`. Comandos v3 ficam separados dos comandos MQTT legados, para
que seu scheduler não altere nem notifique estados da outra versão. Migração
aditiva, sem apagar dados; consultas privadas continuam verificando proprietário
no PostgreSQL. Inbox/efeitos/outbox usam a mesma transação. Não apagar essas
tabelas para reiniciar consumidores: isso elimina deduplicação e comandos pendentes.
O histórico processado ainda não tem expurgo; medir capacidade/retenção na B2-33.

Usar PostgreSQL **descartável** com permissão de criar/apagar bancos. Nunca
fornecer credenciais da base pessoal: os testes criam bancos `b205_<uuid>` e os
removem no teardown. Configure `POSTGRES_TEST_HOST`, `POSTGRES_TEST_PORT`,
`POSTGRES_TEST_DB`, `POSTGRES_TEST_USER`, `POSTGRES_TEST_PASSWORD` fora do Git.

```sh
python -m pytest backend/tests/integration/test_aiot_migrations_integration.py backend/tests/integration/test_postgres_schema_integration.py backend/tests/integration/test_catalog_integration.py backend/tests/api/test_auth_api.py --no-cov -o addopts='' -q
```

As fixtures de demonstração estão em `test_aiot_migrations_integration.py`:
três contas com papéis definidos, ambientes e metadados privados pequenos,
senhas aleatórias hasheadas sem credenciais reutilizáveis. Não são seeds de
produção nem modelos realmente treinados. Os testes comparam todas as tabelas
antigas numa cópia real da fixture legada e provocam falha SQL para verificar
rollback/reaplicação. Resultados atuais e limites estão no cartão B2-05.
