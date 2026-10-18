# Backend

A B2-13 acrescenta consumidor e entrega privada AIoT v3, habilitados explicitamente
por `compose.aiot.yaml`. Regras, comandos e auditoria são transacionais no PostgreSQL;
inbox deduplica eventos e outbox conserva saídas até confirmação AMQP. LED manual
e buzzer automático usam RabbitMQ → gateway; a API não publica MQTT no fluxo v3.
O fluxo legado MQTT v1/v2 continua separado.

Rotas e semântica estão em [contratos AIoT](../contracts/aiot.md#persistência-e-recuperação-http-v3--b2-13).
Operação no [guia de configuração](../docs/configuration.md#api-aiot-opcional-b2-13).
Com AIoT habilitado, readiness também exige as duas conexões AMQP. O histórico
HTTP v3 recupera eventos processados no PostgreSQL e informa `pending/persisted`;
WebSocket só entrega leituras com prova de gravação InfluxDB.

A B2-14 acrescenta contexto/limites ao resumo, períodos ou janela UTC no histórico,
consulta de alertas por intervalo e consulta privada de comando por UUID para o
dashboard. São extensões das rotas v3; nenhuma migração ou dependência nova.

A B2-15 acrescenta `GET /api/v3/messaging`, autorizado pelo papel admin atual
no PostgreSQL. Consulta a Management API por credencial exclusiva, limita os
campos às nove filas do produto e retorna contagens, consumidores e taxas com
`sampled_at`. Não lê mensagens. As métricas são agregadas da infraestrutura,
não filtradas por dispositivo/proprietário; viewer/operator recebem 403.
Falhas do broker retornam 503 sanitizado; sem credencial, a rota não é instalada.
Configuração e isolamento
estão em [Mensageria](../docs/configuration.md#mensageria-b2-15); sem dependência
ou migração nova.

A B2-16 acrescenta `GET /api/v3/messaging/messages`, também admin, mas com
resumos filtrados pelo dono atual do dispositivo/ambiente. O observador consome
somente cópias da fila `observability`; não retira originais da DLQ ou do writer.
Limita a memória a 100 eventos + 100 mensagens mortas, expõe conexão/atualidade
e metadados permitidos (IDs, tipo, horários, origem, motivo/erro), nunca corpos
brutos. Amostras desaparecem ao reiniciar; a DLQ é preservada.
Configuração e limites em [amostras privadas](../docs/configuration.md#amostras-privadas-b2-16).

A B2-17 acrescenta jobs privados com `POST /api/v3/jobs` (admin, `202`),
consulta por UUID e progresso HTTP/SSE autenticado. Job e outbox são atômicos;
AMQP confirma publicação e execução antes do ACK. Workers de geração e treino
compartilham um advisory lock PostgreSQL e retomam contadores duráveis.
Configuração em [jobs](../docs/configuration.md#jobs-assíncronos-b2-17),
contrato em [HTTP de jobs](../contracts/aiot.md#jobs-http-e-progresso-sse--b2-17).
O worker de geração B2-18 já produz datasets offline. A B2-21 acrescenta a etapa
offline de saúde; o job de treino ainda não tem executor do pacote saúde + RUL
e termina `failed` se solicitado por AMQP.

## Laboratório e consulta de datasets B2-19

O router de jobs oferece resumo privado em `GET /api/v3/datasets/{id}` e amostra
separada em `GET /api/v3/datasets/{id}/sample`. Reutiliza dono da sessão, metadados
PostgreSQL e volume de artefatos RO; só resultados de geração concluídos ficam
disponíveis. O job HTTP passa a devolver autor e configuração persistida para
recuperação da página. [Contrato e limites](../contracts/aiot.md#consulta-privada-de-datasets--b2-19).

Qualidade observada conta faltantes e faixas dos sensores selecionados e linhas
com RUL observada/censurada. O leitor verifica os blocos NPY sem carregar o
dataset inteiro; cada consulta de resumo faz leitura proporcional ao volume.
Não usa InfluxDB/MQTT nem publica amostras. NumPy já existente, sem nova dependência.

## Features e preparação de dados B2-20

`domain/features.py` calcula média/desvio/tendência/máximo com um kernel NumPy
compartilhado. `services/feature_inputs.py` adapta NPY e telemetria já autorizada
para o mesmo layout; o eixo online é `received_at`, sem usar relógio do dispositivo.
`domain/feature_preprocessing.py` ajusta mediana e clipping exclusivamente no
treino e exporta estado JSON para aplicação idêntica em validação/teste/online.

`services/training_data.py:prepare_dataset` confere origem/dono/job concluído,
reutiliza o leitor B2-19 e produz uma pasta nova com split 70/15/15 por equipamento,
matrizes NPY e manifesto. Os blocos intercalados mantêm continuidade por máquina;
X exclui IDs/labels e targets mantêm saúde/RUL/máscara de censura separados.
Exige ao menos três equipamentos e recusa treino sem valores úteis. A B2-21
consome essa preparação no treino offline de saúde descrito abaixo.

[Layout, fronteiras de janela, insuficiência e limites](../contracts/aiot.md#features-e-preparação-de-treino--b2-20).
As janelas iniciais são 15 minutos/1 hora, com passado estrito. Uma falha deixa
pasta parcial sem `manifest.json`; não a reutilize nem trate como resultado pronto.
Não há cache de histórico live ou consumidor novo: o chamador online deve entregar
histórico autorizado e ordenado e conferir `sufficient` antes da inferência.

Mapear um arquivo não garante RSS baixo: o sistema pode manter suas páginas
residentes. Por isso o ajuste reúne apenas uma coluna do treino por vez a partir
dos blocos, e a gravação fecha cada mapeamento após seu bloco. A mediana e os
quantis continuam exatos, com custo adicional de percorrer os blocos por coluna.

Testes locais e ensaio com fonte gerada real, da raiz, usando o lock dev:

```sh
python -m pytest backend/tests/domain/test_features.py backend/tests/domain/test_feature_preprocessing.py backend/tests/services/test_training_data.py --no-cov -o addopts='' -q
python -m scripts.benchmark_features --output /tmp/coldsafe-features-1m --total 1000000 --seed 42
```

A pasta de saída precisa ser nova. Para o teto, use outra pasta e `--total 2000000`.
O benchmark confere grupos disjuntos, contagem, finitude, censura, hashes da fonte
e igualdade da primeira linha útil entre artefato de treino e entrada online,
reaplicando o estado salvo. Mede tempo, disco e RSS do processo completo; não
inclui a pilha de serviços nem o custo de treinar modelos. Usa somente NumPy já
instalado, sem pandas/scikit-learn novos. Resultados no [cartão](../docs/aiot/tasks/B2-20.md).

## Treino offline de saúde B2-21

`services.health_training.train_health(prepared, directory, seed=42)` reutiliza
as matrizes/transformação B2-20, ajusta baseline e candidatos apenas no treino,
escolhe pela validação e avalia o teste reservado separadamente. Exemplo: se o
baseline erra 20 pontos de saúde e o candidato erra 5 na mesma validação, o modelo
é apto; empate ou erro maior são rejeitados. A métrica usada é MAE, média do erro
absoluto em pontos na escala 0–100.

O destino deve ser novo e separado da origem. `report.json` marca a conclusão;
`model.pkl` só existe para candidato apto, sem significar ativação ou inferência
no dashboard. São artefatos privados; não carregue pickle externo. O relatório
guarda SHA-256, configuração, divisão, versões, MAE/RMSE/R², tempo e RSS.
[Contrato, decisões e limites](../contracts/aiot.md#regressão-offline-de-saúde--b2-21).

Da raiz, com `backend/requirements-dev.lock.txt` instalado:

```sh
python -m pytest backend/tests/services/test_health_training.py backend/tests/services/test_training_data.py backend/tests/services/test_generation.py --no-cov -o addopts='' -q
python -m scripts.benchmark_health --output /tmp/coldsafe-health-novo-1m --total 1000000 --seed 42
python -m scripts.benchmark_health --prepared /tmp/coldsafe-health-novo-1m/prepared --output /tmp/coldsafe-health-repeticao --seed 42
```

O primeiro ensaio gera/prepara uma fonte sintética com UUIDs determinísticos;
o segundo usa exatamente o mesmo preparo sem regravar os insumos. Compare
`training.metrics`, `training.selection`, `training.input_hashes` e hash do modelo
nos dois `benchmark.json`; tempos/RSS naturalmente diferem. `--total 2000000`
exercita o teto em outra pasta. O fit usa todas as linhas de treino, sem amostragem.
Memória depende de volume/layout; RSS é o máximo do processo, incluindo geração
e preparo quando executados juntos. Fontes/saídas do ensaio são descartáveis.

Nova dependência direta: scikit-learn `1.9.1`; transitivas novas fixadas nos locks:
SciPy `1.18.1`, joblib `1.6.0`, threadpoolctl `3.7.0`, narwhals `2.27.1` e
cloudpickle `3.1.2`. A implementação usa pickle da biblioteca padrão apenas para
gravar o bundle interno; não oferece carregamento de arquivos recebidos.
Job AMQP continua exigindo duas regressões e registro do pacote: saúde isolada
não pode satisfazer esse contrato. Resultados no [cartão B2-21](../docs/aiot/tasks/B2-21.md).

## Treino offline de RUL B2-22

`services.rul_training.train_rul(prepared, directory, seed=42)` estima vida útil
restante em **horas**, usando somente falhas observadas. Por exemplo, uma máquina
que falhou tem tempo até falha conhecido, inclusive zero no instante final; uma
máquina que continuou funcionando ao encerrar a coleta tem duração desconhecida,
e seu alvo censurado não vira zero. Saúde continua usando também os censurados.

Reutiliza o preparo B2-20 e suas máquinas disjuntas. Baseline e candidatos usam
somente treino; validação escolhe/gateia o modelo, e o teste reservado registra
o resultado separado. O relatório inclui o recorte das últimas **24 horas** antes
da falha, definido previamente para expor erros próximos do evento. Previsões
são limitadas apenas em zero: 240 horas continuam 240, sem herdar o teto da saúde.
[Contrato e limites](../contracts/aiot.md#regressão-offline-de-vida-útil-restante--b2-22).

Para comprovar os **dois modelos separados**, execute, da raiz com o lock dev:

```sh
python -m pytest backend/tests/services/test_rul_training.py backend/tests/services/test_health_training.py backend/tests/infra/test_benchmark_rul.py --no-cov -o addopts='' -q
python -m scripts.benchmark_rul --prepared /tmp/coldsafe-health-novo-1m/prepared --output /tmp/coldsafe-rul-par-novo --seed 42
```

O preparo precisa existir; o benchmark de saúde acima pode produzi-lo. Saída
precisa ser nova e separada. O script treina saúde e depois RUL em filhos
separados, sem manter os dois fits na memória. Cada pasta (`health`, `rul`) tem
seu próprio relatório e, se apto, modelo; o `benchmark.json` final confere hashes,
contratos, origem intacta e artefatos distintos. Repita com o mesmo preparo/seed
em outra saída e compare métricas, escolha e hashes; tempos/RSS podem variar.

Nenhuma dependência nova. Essas funções são etapas offline; B2-23 abaixo integra
o executor AMQP e registra seus resultados. O aprendizado apenas com falhas observadas pode
favorecer esse subconjunto: os resultados não comprovam duração de máquinas
censuradas, calibração física ou capacidade da pilha completa. Resultados no
[cartão B2-22](../docs/aiot/tasks/B2-22.md).

## Treinamento integrado e resultados B2-23

`TrainingHandler` liga a fonte privada ao preparo B2-20 e aos dois regressores
em subprocessos sequenciais. O pai conserva o lock PostgreSQL e o progresso;
cada filho usa uma thread. Relatórios recebem dispersão e importância por
permutação em até 500 linhas do teste reservado, três repetições e seed 42,
depois da seleção por validação. Não muda baseline, gate nem métricas completas.

O pacote JSON `training-package-v1` é registrado em `models` para concluir o
job, inclusive quando algum candidato é rejeitado. `eligible` exige ambos aptos;
somente alvos aptos têm pickle. Não existe ativação automática. Leitor de
resultados confere propriedade, identidades, contratos, limites e hashes,
sem desserializar os modelos. `GET /api/v3/datasets` lista fontes concluídas da
conta; `GET /api/v3/jobs/{id}/result` expõe apenas métricas/diagnósticos privados.
Detalhes em [contrato B2-23](../contracts/aiot.md#resultados-e-diagnósticos-de-treinamento--b2-23).

Use o [overlay/configuração de jobs](../docs/configuration.md#jobs-assíncronos-b2-17),
com fontes RO e resultados em volume separado. Não remover tentativas ou
preparos referenciados; não há coleta automática de órfãos. O limite inicial do
worker não comprova capacidade da pilha inteira. Testes direcionados:

```sh
python -m pytest backend/tests/services/test_training.py backend/tests/api/test_training_api.py backend/tests/services/test_regression_diagnostics.py backend/tests/services/test_health_training.py backend/tests/services/test_rul_training.py --no-cov -o addopts='' -q
```

Ensaio real com PostgreSQL de teste, Docker, Node 24/lock frontend e Chromium:

```sh
COLDSAFE_TRAINING_INTEGRATION=1 COLDSAFE_RABBITMQ_INTEGRATION=1 python -m pytest backend/tests/integration/test_training_integration.py --no-cov -o addopts='' -q -s
```

Configure `POSTGRES_TEST_HOST/PORT/DB/USER/PASSWORD` para um PostgreSQL
descartável e `AUTH_JWT_SECRET` de teste (mínimo 32 caracteres). O harness cria e
remove banco/broker/arquivos próprios; nunca usar credenciais pessoais.
`COLDSAFE_NODE_BINARY`/`COLDSAFE_FRONTEND_NODE_MODULES` aceitam runtime/instalação
temporários do mesmo lock. `COLDSAFE_TRAINING_EVIDENCE_DIR` conserva relatórios e
capturas; trate IDs/metadados dessa pasta como dados privados do ensaio.
O teste gera 1m, treina os dois alvos por AMQP, recarrega entre etapas, compara
API/tela/artefatos, verifica isolamento/403 e ausência de ativações. Login HTTP
é real; somente a colocação da sessão no navegador é feita pelo harness.

## Geração offline B2-18

O mesmo POST de jobs aceita os parâmetros documentados no
[contrato](../contracts/aiot.md#jobs-http-e-progresso-sse--b2-17).
`total_units` conta linhas de equipamento: uma linha contém até seis medições,
não seis leituras contadas separadamente. `equipment_count` distribui essas linhas
entre equipamentos sintéticos; quantidade de sensores = equipamentos × tipos
selecionados. IDs sintéticos não são o catálogo de dispositivos live.

O gerador NumPy vetorizado escreve blocos de **50 mil linhas** no volume
`job-artifacts`. Não conecta a MQTT/InfluxDB nem publica amostras/labels no AMQP.
Somente metadados do job e progresso seguem pelas filas existentes. Usa memória
proporcional ao bloco e ao catálogo sintético, sem DataFrame nem concatenação
do dataset inteiro. NumPy `2.5.4` é a única dependência nova.

Cada tentativa cria diretório privado exclusivo e publica `manifest.json` apenas
depois de todos os blocos. Arquivos temporários, rename e fsync protegem a gravação;
só depois o dataset é registrado com dono/job no PostgreSQL. Em falha de escrita
não há resultado concluído. Depois de interrupção, a mesma seed **regera desde o
primeiro bloco**, em novo diretório; checkpoints usam o máximo entre contador
anterior e atual, conferindo a conexão PostgreSQL a cada bloco. UUID do dataset
é estável por job, com um registro atualizado após replay completo.

Tentativas interrompidas podem deixar diretórios órfãos. Não há expurgo automático:
com workers parados, preserve as chaves referenciadas em `datasets.artifact_key`
antes de remover órfãos. Nunca apague volumes pessoais para refazer uma geração.
O lock continua limitado à sessão PostgreSQL viva: se ela cair, o cálculo só para
no próximo checkpoint; diretórios exclusivos impedem mistura de arquivos, sem
prometer exclusão de CPU durante essa janela.

O manifesto registra seed/configuração completa, versão do armazenamento/NumPy,
unidades, UUIDs e modos de cada equipamento, contagem/nome/SHA-256 dos blocos.
Formato `offline-numpy-v1`: NPY estruturado little-endian, `equipment_index:int32`
referencia a lista do manifesto, `observed_at:datetime64[ms]` UTC a partir de
2026-01-01, seis medições float64 e labels float64/bool conforme schema offline.
Sempre carregar com `np.load(..., allow_pickle=False)` e iterar bloco a bloco;
`mmap_mode='r'` permite inspeção sem carregar o arquivo todo. Na linha lógica,
NaN vira JSON `null`; dataset_id vem do manifesto e equipment_id da lista.

Há ciclo diário, variação de baseline/fase por equipamento, modos normal/heavy/
cycling, rolamento/desbalanceamento progressivos, ruído, faltantes e outliers.
Direções físicas seguem o simulador (desgaste aumenta corrente, vibração,
temperatura do motor e perda térmica), mas o modelo massivo é vetorizado, sem
equivalência exata com a recorrência térmica da borda. Equipamentos observados
terminam na falha; os censurados param no fim da janela sem inventar sua RUL.
`degradation_true` vai de 0 a 1; saúde = `100*(1-degradation_true)`.
Medições têm heterogeneidade e ruído com sobreposição. Sensores não selecionados
ficam NaN; outliers offline podem exceder limites live. Não são dados calibrados
nem validação de precisão industrial. A seleção `failure_fraction` é probabilística
por equipamento; não promete percentual exato em catálogos pequenos.

Para reproduzir a medição em um processo novo, na raiz e com o lock dev instalado:

```sh
python -m scripts.benchmark_generation --output /tmp/coldsafe-dataset-1m --total 1000000 --seed 42
python -m pytest backend/tests/services/test_generation.py --no-cov -o addopts='' -q
```

O diretório de saída precisa ser novo. O script verifica hashes, contagem,
censura/saúde e relata pico RSS do processo inteiro (não só arrays), tempo e
bytes em disco. Troque `--total` por `2000000` para o teto. Duas execuções com
mesma seed/configuração/versão reproduzem bytes dos blocos; UUIDs/metadados de
datasets diferentes podem mudar. Evidência medida em [B2-18](../docs/aiot/tasks/B2-18.md).
Os testes de integração requerem PostgreSQL descartável (`POSTGRES_TEST_*`);
`COLDSAFE_RABBITMQ_INTEGRATION=1` habilita também o ensaio com broker descartável.

Esta área contém a ingestão MQTT, a classificação das leituras, a persistência no
InfluxDB, a estrutura relacional PostgreSQL e a API FastAPI.

Na inicialização, `app/repositories/postgres.py` aplica em transação as migrações
versionadas em `migrations/`. O PostgreSQL guarda usuários,
sessões, ambientes, dispositivos, regras, alertas, comandos e auditoria;
leituras antigas continuam no InfluxDB. O readiness exige conexão com os dois
bancos e com o MQTT.

As versões 004–005 acrescentam papéis e metadados privados de jobs, datasets,
modelos e ativação por proprietário. A versão 006 acrescenta identificação de
sessões JWT, limites de login e tickets WebSocket. O [guia de migrações](migrations/README.md)
explica propriedade, backup e recuperação. A persistência prepara o AIoT;
workers de jobs estão na B2-17, geração offline na B2-18 e saúde/RUL offline nas B2-21/22;
pacote de treino integrado e inferência continuam posteriores. Autenticação e
permissões atuais estão no [guia de segurança](../docs/aiot/tasks/B2-06.md).

A primeira implementação do domínio está em `app/domain/telemetry.py`. Ela transforma
bytes MQTT não confiáveis em um `TelemetryPayload` estrito e imutável, rejeitando
campos ausentes ou extras, tipos incorretos, números não finitos e valores fora dos
limites técnicos. Mensagens maiores que 1 KiB são recusadas antes do parse para
limitar consumo de CPU e memória na fronteira MQTT.

O processo executável está em `app/main.py`. Ele valida as variáveis de ambiente,
inicia o assinante MQTT, fecha os recursos no desligamento e expõe:

- cadastro, login e logout em `/api/v1/auth/`;
- ambientes, dispositivos e regras em `/api/v1/`;
- `GET /api/v1/monitoring/summary`, `GET /api/v1/readings` e `GET /api/v1/alerts`;
- `POST /api/v1/devices/{id}/led/commands` e `GET /api/v1/commands/{id}`;
- `WS /api/v1/events?device_id=...`;
- `GET /health/live` e `GET /health/ready`.

O bloco 2 acrescenta `POST /api/v1/auth/register`, `/login` e `/logout`, com
JWT Bearer revogáveis de 24 horas; rotas REST para ambientes, dispositivos
e limites. `DELETE /api/v1/devices/{id}` desativa sem apagar o histórico. O
OpenAPI executável em `/openapi.json` lista os corpos e métodos completos.

Resumo e histórico aceitam `device_id` MQTT e exigem sessão do proprietário.
Sem `device_id`, o resumo seleciona `esp32-lab-01`, ainda sujeito à mesma
autorização; se não pertencer à conta, a resposta é `404`.
Dispositivos desativados mantêm consultas históricas, mas deixam de aceitar
telemetria. Os limites por ambiente são persistidos em `environment_rules` e
usados na classificação de novas leituras; as regras antigas por dispositivo
foram preservadas na migração. A interface de login e seleção de dispositivo
já usa essas rotas. `/auth/me` consulta o papel atual; administrador pode alterar
papéis em `PATCH /auth/users/{id}/role`, com auditoria, sem acessar dados alheios.
Visualizador lê seus dados; operador/administrador também escrevem nos próprios
ambientes. Cadastro público não escolhe papel. Novos hashes usam bcrypt; login
Argon2 antigo continua válido, sem truncar senhas longas. Limite de login:
10 tentativas por email e 50 por IP em 15 minutos, incluindo sucessos.

`POST /api/v1/auth/ws-ticket` recebe Bearer e `device_id`, devolvendo um ticket
de até 60 segundos. WebSocket envia somente `{ticket}` no primeiro frame;
URL contém apenas `device_id`. Eventos só são enviados após verificar sessão e
propriedade; a conexão é encerrada quando a sessão deixa de ser válida. Ao
reconectar, o cliente usa REST para recuperar o estado que pode ter perdido.

Os erros públicos usam envelopes estáveis e não expõem stack trace, token, payload
ou endereço interno.

Na telemetria v2, o assinante separa os dispositivos por tópico. O InfluxDB
mantém as leituras; PostgreSQL guarda o ciclo dos alertas, os comandos e a
auditoria. Buzzer automático respeita os limites do ambiente e a margem de
recuperação. Um comando LED publicado fica pendente até receber confirmação;
após 30 segundos sem ela, o estado é `unconfirmed`.
