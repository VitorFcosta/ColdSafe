# Simulador B2-09/10

Produtor MQTT v3 independente do backend v1/v2. Publica seis medições por leitura,
com IDs/unidades do [contrato](../contracts/aiot.md). O perfil Compose `simulator`
é opcional: o dashboard atual ainda não recebe v3. O [gateway B2-11](../gateway/README.md)
liga MQTT ao RabbitMQ; gravador e entrega continuam posteriores. O simulador não usa AMQP diretamente.

## Cadastro e execução

`catalog.json` é o cadastro local de comissionamento da borda, montado somente
para leitura. Ele registra dispositivo, ambiente, equipamento, seis sensores e
dois atuadores, com UUIDs distintos. O processo valida o cadastro antes de conectar,
copia esses IDs para cada mensagem e nunca aceita substituições por comandos.
`catalog.example.json` contém IDs fictícios apenas para o ensaio isolado.

Para uso com o catálogo da aplicação, cadastre `sim-lab-01` em um ambiente privado
pela API/tela existente. Preencha `device_record_id` e `environment_id` com os IDs
retornados pelo cadastro. Registre equipamento/sensores/atuadores no arquivo local;
essas entidades ainda não têm tabelas/API no produto. O simulador não consulta
PostgreSQL nem comprova propriedade: o gateway B2-11 verifica o vínculo
confiável antes de aceitar telemetria na aplicação. Não use UUIDs de outro ambiente.

1. Execute `python3 scripts/generate-secrets.py`: acrescenta duas senhas ausentes,
   distintas e privadas, sem rotacionar valores existentes. Não publica segredos.
2. Crie `simulator/local/`, copie o exemplo para `simulator/local/catalog.json`
   e ajuste os IDs conforme o cadastro acima. Para o ensaio exclusivamente local,
   os IDs demonstrativos podem ser mantidos. A pasta está excluída de Git e Docker.
   O arquivo/diretório precisam ser legíveis pelo UID `65532` do container;
   não coloque segredos dentro deles.
3. Atualize a imagem, os arquivos de autenticação e o broker, preservando os volumes:

   ```sh
   docker compose up -d --build --force-recreate mosquitto-init mosquitto
   docker compose --profile simulator up -d --build simulator
   ```

   Reiniciar o broker interrompe brevemente conexões MQTT, que depois reconectam.
   Não use `down --volumes` na pilha pessoal. Um arquivo ausente/inválido impede
   o simulador de iniciar; o Compose não cria o diretório silenciosamente.

4. Para encerrar só este processo: `docker compose stop simulator`.
   Recomeçar o processo reinicia desgaste, semente e controles em memória.

A ACL atual provisiona **um dispositivo live: `sim-lab-01`**. O modelo Python
aceita outros catálogos para testes/reutilização futura; a conexão live rejeita
outra identidade até adicionar sua própria credencial/ACL. Não compartilhe a senha
entre dispositivos. `MQTT_SIMULATOR_PASSWORD` autentica `sim-lab-01`;
`MQTT_SIMULATOR_OPERATOR_PASSWORD` autentica `coldsafe-simulator-operator`.
Os campos novos são opcionais para a pilha v1/v2; vazios não criam essas contas.

## Modelo e tempo

Por padrão, cada segundo real produz um passo de um segundo simulado.
`SIMULATOR_INTERVAL_SECONDS` admite 0,1–60 s e `SIMULATOR_STEP_SECONDS` admite
um passo positivo de até 3600 s. Para acelerar o ensaio, configure passo `60`:
60 segundos simulados por publicação. `occurred_at` continua sendo UTC real,
sem datas futuras; a progressão acelerada existe apenas dentro do modelo.
Semente padrão `42`; uma execução local aceita `--seed`.
A semente reproduz as medições, não UUIDs de evento nem relógio de parede.

Desgaste normal de rolamento e desbalanceamento crescem separadamente.
`inject_fault` aumenta a taxa do modo escolhido para `0,6/h`, sem salto instantâneo.
Vibração, corrente e temperatura do motor dependem dos dois estados; a perda de
eficiência aumenta a temperatura ambiente com resposta térmica gradual de 300 s.
Umidade e luminosidade têm seus próprios ciclos/ruídos. Cada função recebe ruído
independente e permanece nas faixas técnicas do schema. As equações são
**demonstrativas, sem calibração industrial nem validação física**. Não representam
vida útil real nem precisão de um futuro modelo de IA.

`equipment.running=true` representa o ventilador simulado em operação. Parar a
simulação interrompe publicações e progressão, sem criar comando manual para
ventilador e sem inventar leitura de equipamento parado. LED/buzzer começam
`false`; a B2-10 aplica comandos v3 e publica ACK. Estado latente, labels e RUL verdadeira
nunca são serializados em telemetria.

## Controles autorizados do operador

Tópico operacional: `coldsafe/simulator/devices/sim-lab-01/control`.
Somente `coldsafe-simulator-operator` publica; o dispositivo só lê.
Esse canal controla a execução da simulação. Ele não é o `command` v3 de atuadores
nem substitui a futura autenticação/propriedade HTTP. O backend e as identidades
ESP32 não possuem acesso ao tópico ou às leituras deste simulador.

Formato fechado: `command_id` UUID, `device_id`, `action=start|stop|inject_fault`,
`fault=null|bearing_wear|imbalance`, `issued_at` e `expires_at` UTC com prazo de
30 s. A CLI emite horários com precisão de segundos, suficiente para o controle
operacional, reduzindo a sensibilidade a pequenos desvios host/VM; isso não substitui
sincronização UTC. O receptor continua recusando comandos futuros/expirados.
Falha é obrigatória apenas em `inject_fault`. A CLI produz esse formato:

```sh
# Disponibilize a senha do operador em variável exportada na sessão privada.
# -e passa o nome; o valor não entra nos argumentos do comando.
docker compose --profile simulator run --rm --no-deps \
  --entrypoint python -e MQTT_SIMULATOR_OPERATOR_PASSWORD simulator \
  -m simulator.control stop
# Troque stop por start para retomar; para acelerar desgaste:
docker compose --profile simulator run --rm --no-deps \
  --entrypoint python -e MQTT_SIMULATOR_OPERATOR_PASSWORD simulator \
  -m simulator.control inject_fault --fault bearing_wear
```

A senha deve vir do `.env` privado e ser exportada na sessão que chama a CLI;
o Compose não a entrega ao processo normal do dispositivo. Há dois modos de falha:
`bearing_wear` e `imbalance`. A CLI confirma somente aceite do broker; observe a
telemetria para conferir o efeito. Não existe ACK operacional nesta tarefa.

O receptor exige QoS 1, tópico/dispositivo corretos, JSON UTF-8 estrito de até
8192 bytes, schema fechado, horário válido e `retain=false`. MQTT 5 preserva
RETAIN em entrega live e não reproduz controles retidos ao assinar/reconectar.
Duplicatas válidas são ignoradas por ID até seu prazo. Cache limita 256 comandos
simultaneamente válidos e recusa excesso sem expulsar IDs ainda ativos.
Campos extras, modo desconhecido, comando futuro/expirado, JSON duplicado e
labels são rejeitados sem registrar payload ou senha.

## Atuadores e ACK — B2-10

O simulador assina também `coldsafe/v3/devices/sim-lab-01/commands` e publica
`coldsafe/v3/devices/sim-lab-01/acks`. Somente a identidade confiável
`coldsafe-gateway` publica comandos; o dispositivo publica ACK; o gateway lê ACK
para validar o resultado. O operador da simulação e o backend v1/v2 não ganham
essas permissões. `MQTT_GATEWAY_PASSWORD` é uma senha própria, diferente da
senha AMQP `RABBITMQ_GATEWAY_PASSWORD`, gerada pelo mesmo script idempotente.
A conta só é criada quando preenchida; o serviço gateway é implementado na
B2-11. Esta borda não cria API nem comprova autorização por usuário/proprietário.

Os comandos seguem o schema v3 existente: `desired_state` booleano explícito,
`led/manual` ou `buzzer/automatic`. Dispositivo, registro e ambiente devem
coincidir com o cadastro local. Atuador deve coincidir com seu ID cadastrado;
correlação deve ser o ID do comando. Prazo é emissão + 30 s; recebimento confiável
não pode preceder emissão, superar o prazo nem estar no futuro para o equipamento.
O relógio UTC da borda/gateway precisa estar sincronizado.

LED altera `actual_state` e acrescenta 40 pontos percentuais à luminosidade,
respeitando a faixa do schema. Buzzer altera `actual_state`; não inventa som ou
valor de sensor. Leituras geradas depois da atuação refletem esses estados.
Não há comando manual de ventilador nem regra automática de buzzer na borda:
a regra autorizada será implementada no consumidor/API de negócio.

ACK v3 usa comando/atuador/correlação corretos, UUID próprio, `received_at=null`,
QoS 1 e sem retain. `applied` relata o estado explicitamente aplicado;
`rejected` traz estado nulo e motivo `INVALID_COMMAND`, `EXPIRED_COMMAND` ou
`ACTUATOR_FAILURE`. Cadastro/tempo/relações inválidas em comando estruturalmente
válido recebem rejeição. JSON/schema/UUID inválidos, escopo alheio, QoS errado ou
mensagem retida são descartados sem fabricar um ACK ou ecoar dados de outro escopo.

Idempotência preserva o comando inteiro e seu ACK por `command_id`. Repetição
idêntica dentro do prazo reenvia o mesmo ACK/event_id sem reaplicar o estado;
logo, repetir um "ligar" antigo depois de um "desligar" novo não religa o LED.
Alterar conteúdo/prazo com o mesmo ID, ou reutilizar event_id para outro comando,
gera `INVALID_COMMAND`. Repetição após o prazo recebe `EXPIRED_COMMAND`, nunca
um novo sucesso. O ACK reenviado é o resultado original, não um retrato do estado
atual; gateway precisa tratar duplicatas e verificar o horário confiável de chegada.

Cache mantém no máximo **256 comandos aceitos por processo**, sem expulsar IDs
antigos: capacidade esgotada recusa novos com `ACTUATOR_FAILURE`. Estado e cache
não sobrevivem a restart. Antes de escalar/usar em produção, persistir ambos e
completar estado durável no serviço de comandos. Gateway B2-11 já conserva
deduplicação/transporte em SQLite; isso não persiste o estado físico do simulador. Restart
reinicia LED/buzzer em false e desgaste. Há limite explícito, sem promessa de
atuação exatamente uma vez entre falhas de processo.

A callback publica ACK sem esperar PUBACK, para não bloquear o loop Paho. Se a
fila estiver cheia, registra somente diagnóstico sanitizado; a atuação já realizada
não é revertida nem declarada confirmada ao consumidor. Retry do mesmo comando
válido pode recuperar o ACK original. Publicar comando no broker **não confirma
atuação**: sem ACK compatível no prazo, o futuro serviço deve conservar ausência
de confirmação. Um ACK tardio não autoriza transformar timeout persistido em sucesso.
O simulador não emite `command_status` nem mantém a máquina de timeout da API.

## Telemetria e recuperação

Publica `coldsafe/v3/devices/sim-lab-01/telemetry` com QoS 1 e `retain=false`.
Cada evento tem UUID próprio, `correlation_id=event_id` e `received_at=null`.
As seis funções/IDs são independentes; temperatura ambiente não substitui motor.
O schema compartilhado valida cada evento antes de publicar.

Paho reconecta com atraso exponencial de 1–10 s e reinscreve o controle; só começa
a publicar após SUBACK aceito. Desconexão pausa geração e desgaste. A fila de saída
é limitada a 16 mensagens compartilhadas entre telemetria e ACK; uma mensagem
pendente pode ser retransmitida com o mesmo ID. Não é buffer durável nem gravação sem perdas; o gateway deve tratar duplicatas,
horário de aceite e freshness. SIGINT/SIGTERM desconecta e encerra o loop.
O container roda sem root, sem portas, em rede interna, read-only, limitado a
64 MiB/0,25 CPU. Não extrapole esse ensaio para a capacidade da pilha completa.

## Dependências e testes

`requirements.txt` fixa paho-mqtt `2.1.0` e jsonschema `4.26.0` e suas quatro
transitivas, reutilizando versões do lock dev existente. Nenhuma biblioteca nova
no projeto; jsonschema passa a executar também no container do simulador.
Python usa a mesma imagem `3.13.15-slim` do backend.

```sh
python -m pytest backend/tests/infra/test_simulator.py \
  backend/tests/infra/test_simulator_actuators.py --no-cov -o addopts='' -q
COLDSAFE_SIMULATOR_INTEGRATION=1 python -m pytest \
  backend/tests/infra/test_simulator_integration.py --no-cov -o addopts='' -q
```

Use o ambiente do lock dev. O segundo comando cria imagens/credenciais/volumes
novos com prefixo `coldsafe-b209-*`, inspeciona MQTT real e remove containers e
volumes no `finally`. Não consulta `.env` pessoal nem inicia a pilha de produto.
Confere schema/IDs, efeito gradual, parar/retomar, RETAIN, ACL de publicação/leitura,
senha errada/anônimo, CLI, restart, LED/luz/buzzer, ACK/idempotência/rejeição,
ausência de ACK com dispositivo parado, retry expirado e limites do container.

Referências oficiais conferidas em 14/10/2026: [Paho Client API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
(loop, reconexão, MQTT 5 e SubscribeOptions) e [ACL Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html)
(permissões por username). Resultados e limites ficam nos cartões [B2-09](../docs/aiot/tasks/B2-09.md) e
[B2-10](../docs/aiot/tasks/B2-10.md).
