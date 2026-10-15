# Arquitetura alvo AIoT

**Arquitetura alvo, ainda não implementada.** Setas mostram protocolos e responsabilidades. Mosquitto é a borda IoT; RabbitMQ distribui eventos internos; REST consulta os bancos pela API.

B2-11 implementa o trecho simulador ↔ Mosquitto ↔ gateway ↔ RabbitMQ, incluindo
diário privado e validação de propriedade PostgreSQL. Os demais fluxos abaixo
continuam como alvo; o gravador, consumidores de negócio e API v3 são posteriores.

## Visão geral

```mermaid
flowchart LR
subgraph BORDA["Borda IoT"]
SIM["Simulador Python"] <-->|MQTT| MOS["Mosquitto"]
MOS <-->|MQTT| GW["Gateway"]
end
subgraph INTERNO["Serviços internos"]
GW <-->|AMQP| RAB["RabbitMQ topic"]
RAB --> GR["Gravador"]
GR --> INF[("InfluxDB")]
RAB --> IA["Inferência"]
IA -->|Previsões| RAB
RAB --> LAB["Geração e treino"]
LAB -->|Progresso e resultados| RAB
LAB --> MOD["Modelos versionados"]
MOD --> IA
RAB <-->|Eventos e comandos| API["FastAPI"]
API <--> PG[("PostgreSQL")]
API -->|Histórico| INF
API <--> LLM["Ollama CPU"]
end
WEB["Vue: dashboard e 3D"] <-->|REST e WebSocket| API
```
## Telemetria e previsões

```mermaid
sequenceDiagram
participant S as Simulador
participant M as Mosquitto
participant G as Gateway
participant R as RabbitMQ
participant W as Gravador
participant I as Inferência
participant A as FastAPI
participant F as Vue e 3D
S->>M: Sensores e estado dos atuadores
M->>G: MQTT autenticado
G->>R: Evento JSON validado
par Persistir
R->>W: Fila de gravação
W->>W: Gravar InfluxDB e confirmar
and Prever
R->>I: Fila de inferência
I->>R: Saúde, RUL, versão ou indisponível
and Entregar
R->>A: Fila de eventos autorizados
A->>F: WebSocket
end
R->>A: Previsões e alertas
A->>F: Atualizar insights e cores
```
A entrega de telemetria e de previsão é assíncrona: a interface correlaciona equipamento e instante, sem atribuir previsão antiga a leitura nova. Sem modelo/histórico, mostra indisponibilidade. REST de histórico não contorna o RabbitMQ na ingestão.

O paralelismo do desenho representa responsabilidades, não autorização para
entregar uma leitura antes da persistência. A entrega Web segue a condição de
leitura validada e persistida definida no [contrato v3](../../contracts/aiot.md).
## Comando e confirmação

```mermaid
sequenceDiagram
participant U as Usuário
participant F as Vue
participant A as FastAPI
participant R as RabbitMQ
participant G as Gateway
participant M as Mosquitto
participant S as Simulador
U->>F: Ligar LED
F->>A: Solicitar estado
A->>A: Verificar papel/proprietário e registrar pendente
A->>R: Comando correlacionado
R->>G: Fila de comandos
G->>M: MQTT
M->>S: Aplicar estado
S->>M: ACK e próxima telemetria
M->>G: Confirmação
G->>R: Evento de ACK
R->>A: Confirmar resultado e auditar
A->>F: WebSocket com estado final
```
A automação do buzzer usa o mesmo caminho de comando, iniciada pela regra. Publicação não é confirmação de atuação. Repetir ID não deve aplicar o comando duas vezes.
## Geração, treino e ativação

```mermaid
sequenceDiagram
participant F as Laboratório Web
participant A as FastAPI
participant R as RabbitMQ
participant G as Gerador
participant T as Treinador
participant V as Volume de artefatos
participant I as Inferência
F->>A: Configuração e seed
A->>R: Job de geração autorizado
R->>G: Executar em blocos
G->>V: Dataset offline com labels
G->>R: Progresso e conclusão
R->>A: Atualizar job
A->>F: Progresso por WebSocket
F->>A: Treinar dataset
A->>R: Job de treino
R->>T: Um job pesado por vez
T->>V: Dois modelos, métricas e versões
T->>R: Candidato avaliado
R->>A: Mostrar métricas
A->>R: Ativar versão aprovada
R->>I: Recarregar sem reiniciar
I->>V: Ler bundle completo
```
## Fronteiras e revisão

- Navegador acessa somente ColdSafe; não acessa brokers, bancos ou Ollama diretamente.
- InfluxDB guarda telemetria. PostgreSQL guarda propriedade, regras, auditoria, jobs e metadados.
- Datasets e modelos em volumes separados; labels nunca trafegam na telemetria ao vivo.
- Filas duráveis, confirmações e DLQ; observabilidade não retira mensagens das filas de negócio.
- Um host é ponto único de falha nesta entrega acadêmica; testar recuperação, não acrescentar cluster.
- Ollama descarregado durante jobs pesados; dimensão dos blocos e concorrência condicionadas ao teste de 8 GB.
