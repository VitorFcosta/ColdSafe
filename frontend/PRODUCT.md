# ColdSafe — definição do produto frontend

## Integração AIoT B2-14 — 15/10/2026

O modo AIoT explícito conserva o dashboard e os seletores de conta, ambiente,
dispositivo e período. Acrescenta vibração RMS (`mm/s`), corrente do motor (`A`)
e temperatura do motor (`°C`) à temperatura ambiente, umidade e luz. Gráfico,
resumo textual e tabela acompanham a grandeza selecionada; os limites ambientais
somente aparecem na temperatura ambiente. Dados antigos não recebem sensores
inventados nem zeros para valores ausentes.

O estado observado de LED/buzzer pertence à última telemetria e à sua idade.
O estado do pedido permanece `pending`, `confirmed`, `rejected` ou `unconfirmed`;
um envio ao broker não confirma atuação. Visualizador lê, sem controle manual;
operador/admin comanda somente LED próprio. Buzzer continua automático. Reentrega
WS v3 invalida REST e não aplica status antigo diretamente. Na reconexão,
resumo, atuadores, histórico e alertas/comparação são recuperados.

Essa integração usa o catálogo comissionado de um equipamento/dono por runtime,
conforme B2-13. Não inclui IA, cena 3D nem novos painéis de filas.

## Previsão do equipamento B2-25 — 19/10/2026

O dashboard AIoT acrescenta saúde 0–100 e RUL em horas, com versão e horários da
previsão e da entrada que a originou. Zero é válido; falta de modelo, warm-up,
features inválidas, erro de modelo e leitura vencida são estados textuais.
Só a previsão vinculada à leitura atual pode fornecer valores. Receber previsão
não renova a atualidade dos sensores, e o estado local stale oculta esses números.
A versão muda sem recarregar a página após ativação administrativa autorizada.

As janelas padrão continuam 15 min/1 h. Sem histórico prévio, o primeiro resultado
pode exigir uma hora de coleta. São estimativas sintéticas ainda sem calibração
física. A ativação permanece na API; Insights/alertas preditivos são B2-26.

## Insights B2-26 — 19/10/2026

`/insights` apresenta saúde, RUL, versão, idade, tendência observada e alertas
preditivos persistidos do equipamento autorizado. Falta de previsão e leitura
vencida permanecem explícitas; não representam recuperação. Operador/admin pode
editar regras do proprietário, com 3 críticas para abrir e 10 recuperadas para
encerrar inicialmente. O buzzer continua ligado exclusivamente à regra térmica.
Os limites iniciais são de protótipo e exigem calibração para uso operacional.

## Gêmeo digital B2-27 — 19/10/2026

`/digital-twin` mostra o ventilador, seis sensores, LED e buzzer em geometria
simples. Inventário autorizado identifica os nove itens mesmo sem leituras;
posições ilustrativas pertencem somente ao frontend. A lista de botões oferece
seleção por teclado equivalente ao clique 3D, com nome, ID, valor e estado textual.
Leituras/estados vêm do resumo recuperado por eventos WebSocket; não há simulação
local. Temperatura usa regras do ambiente; ventilador usa alerta/faixas preditivas;
LED/buzzer usam telemetria observada. Os demais sensores não possuem faixas
operacionais, e “Normal” nesses itens significa apenas dado atual recebido.
Ausência, vencimento, falha de consulta e falha WebGL ficam explícitos.

Three.js direto no Vue, com descarte de recursos ao desmontar. Dependências
fixadas: `three 0.186.1` e `@types/three 0.186.0`.

Na B2-28, giro acompanha funcionamento observado e tremor acompanha vibração;
LED brilha e buzzer ligado tem pulso suave de 1 Hz, sem áudio. A luminosidade
percentual muda a iluminação; temperatura ambiente muda a barra térmica superior.
Giro/tremor e escala térmica são ilustrativos, sem calibração física ou RPM medido.
Leitura vencida após 30 s congela movimento e avisa, mesmo com WebSocket aberto;
a aparência ambiental conservada identifica a última leitura. Dados novos retomam
sem compensar o intervalo parado. Preferência de movimento reduzido e aba oculta
suspendem o loop; valores e estados continuam disponíveis na lista.
Na B2-29, seleção por clique/lista abre última leitura, idade, horário e gráfico
por ID. Saúde/RUL de sensores/atuadores são não aplicáveis; a previsão do
equipamento aparece separadamente. O LED usa o mesmo controle/ACK do dashboard,
com permissões e erros explícitos; buzzer permanece automático. Histórico de
estado dos atuadores não existe: o gráfico contextual de temperatura ambiente
do equipamento associado é identificado, sem inferir estado a partir dele.

## Propósito

Na B2-15, `/messaging` acrescenta um painel administrativo de infraestrutura:
filas compartilhadas, contagens, taxas e consumidores reais. Polling passa pela
API ColdSafe, com idade da coleta e falhas explícitas. Viewer/operator não recebem
essas métricas agregadas. A B2-16 acrescenta resumos privados das últimas mensagens
e de cópias da DLQ, filtrados pelo proprietário atual, com origem/motivo e estado
do observador. O painel não expõe corpos brutos, credenciais nem controle Docker.

O frontend do ColdSafe é um dashboard operacional acadêmico para reconhecer,
em poucos segundos, o estado do ambiente refrigerado selecionado, a atualidade
da última leitura e a variação recente da temperatura.

O dashboard também serve como prova visível da cadeia DHT22 → ESP32 → MQTT →
FastAPI → InfluxDB → API → Vue.

> O ColdSafe é um protótipo acadêmico. Ele não é equipamento médico, sistema
> sanitário certificado nem substitui procedimentos oficiais de controle.

## Contrato vigente para o redesign visual (27/09/2026)

As seções sobre o primeiro bimestre abaixo registram o escopo histórico do MVP.
Para o redesign, prevalecem o [roadmap visual](https://app.notion.com/p/3e8d67001da981d4a27fed1418af291e),
o código atual e os [contratos compartilhados](../contracts/README.md).

| Rota | Função atual a preservar |
| --- | --- |
| `/` | Apresentação acadêmica escura, demonstração identificada como simulada, vídeo com legendas e caminho para o painel. |
| `/login` | Entrada e cadastro da conta. |
| `/dashboard` | Seleção de ambiente/dispositivo, leitura, alertas, histórico, comparação, atuadores e previsão vinculada no modo AIoT. |
| `/manage` | Cadastro e edição de ambientes, dispositivos e limites. |
| `/messaging` | Métricas administrativas reais de filas, taxas e consumidores, com idade da coleta. |
| `/laboratory` | Geração sintética privada, progresso recuperável, resumo e amostra; formulário administrativo. |
| `/training` | Avaliação administrativa de saúde/RUL: dataset próprio, job, baseline, erros, gráficos e importância; pacote permanece offline. |
| `/insights` | Saúde/RUL, tendência, idade e alertas preditivos privados; regras editáveis por operador/admin. |

`/dashboard` e `/manage` exigem sessão. A operação usa dados reais da API, com
dois dispositivos simulados no projeto; o histórico oferece **15 min, 1 h, 6 h e
24 h**. O WebSocket atualiza eventos, e a reconexão recupera o estado por REST.
Uma conexão com o servidor não confirma leitura recente nem atuação do LED:
comandos podem estar pendentes, confirmados, rejeitados ou sem confirmação.
Leitura antiga, ausência de dados, carregamento, erro e falha parcial devem
continuar distinguíveis por texto, inclusive no celular.

As duas imagens do roadmap são **propostas com dados simulados**: orientam a
hierarquia visual, sem substituir os valores da API. A composição móvel resume
controles, mas a implementação mantém troca de ambiente e dispositivo, os
quatro períodos, alertas, comparação e tabela de leituras. A landing conserva
o conteúdo acadêmico, a mídia e o rodapé.
Referências de regressão: `e2e/landing.spec.ts`, `e2e/dashboard.spec.ts` e os
testes unitários de estado, histórico, comandos e formulários. Não há biblioteca
nova prevista para este contrato.

## Para quem é

- **Usuário primário:** operador de laboratório acadêmico sob pressão moderada.
- **Stakeholder da entrega:** avaliador acadêmico que precisa verificar o fluxo
  IoT completo e a correspondência entre telemetria, histórico e interface.

## Problema que o MVP resolve

Verificações manuais e registros dispersos atrasam a identificação de uma
temperatura inadequada. Sem histórico e sem indicação de atualidade, o operador
também não sabe se está observando um valor recente ou uma leitura antiga.

O MVP deve responder claramente:

1. Qual é a situação atual do ambiente?
2. Qual foi a última temperatura e umidade recebidas?
3. Há quanto tempo essa leitura chegou?
4. Como a temperatura variou no período selecionado?
5. A cadeia técnica está fornecendo dados confiáveis agora?

## Resultado esperado

No primeiro viewport, o operador deve identificar o ambiente, o dispositivo, a
situação atual, a temperatura, a umidade e a atualidade da leitura. O histórico
deve permitir comparar os períodos de 15 minutos, 1 hora, 6 horas e 24 horas.

O diagnóstico técnico pode existir em uma área secundária, mas não deve competir
com a leitura operacional.

## Histórico: escopo do primeiro bimestre

- Um ambiente: `Laboratório Refrigerado`.
- Um dispositivo: `esp32-lab-01`.
- Dashboard operacional em `/dashboard` e apresentação de portfólio em `/`.
- Temperatura, umidade, horário da leitura, estado e freshness.
- Histórico de temperatura nos períodos `15m`, `1h`, `6h` e `24h`.
- Atualização por polling a cada 5 segundos.
- Estados explícitos de carregamento, ausência de dados, operação normal,
  atenção, criticidade, leitura desatualizada e erro de serviço.
- Falha parcial: se o histórico falhar, a leitura atual válida permanece visível.
- Diagnóstico técnico recolhível para apoiar a demonstração.
- Layout responsivo para desktop e mobile.
- Informação compreensível sem depender apenas de cor.

## Histórico: fora do MVP

- Autenticação e gestão de usuários.
- Múltiplos ambientes ou dispositivos.
- Cadastro, edição ou remoção de entidades.
- Configuração de limites pelo dashboard.
- PostgreSQL, WebSocket ou Pinia.
- Alertas externos e notificações.
- Aplicativo móvel nativo.
- Relé, buzzer, controle de refrigeração ou comandos remotos.
- Inteligência artificial.

Essas exclusões são limites do produto, não espaços reservados na navegação.

## Estados apresentados

| Estado | Significado para o operador | Prioridade da mensagem |
| --- | --- | --- |
| `loading` | A consulta ainda não terminou | Preservar a estrutura e indicar carregamento |
| `no_data` | Nenhuma leitura válida existe | Explicar como iniciar a simulação |
| `normal` | Temperatura dentro da faixa e longe das margens | Confirmar operação demonstrativa normal |
| `attention` | Temperatura próxima de um limite | Destacar observação necessária |
| `critical` | Temperatura fora da faixa demonstrativa | Mostrar condição inadequada e ação compatível com o protótipo |
| `stale` | A última leitura tem mais de 30 segundos | Priorizar a idade da leitura |
| `service_error` | A API ou uma dependência não pôde responder | Informar indisponibilidade sem inventar dados |

A precedência vem do backend: erro de serviço, ausência de dados, leitura
desatualizada e, por último, classificação da temperatura.

## Dados e contratos

O frontend consome somente a API FastAPI. Ele nunca acessa o InfluxDB ou o
Mosquitto diretamente.

- `GET /api/v1/monitoring/summary`: ambiente, dispositivo, leitura atual,
  estado, freshness e limites demonstrativos.
- `GET /api/v1/readings?device_id=esp32-lab-01&period=<period>&limit=<limit>`:
  histórico do dispositivo.
- `GET /health/live`: processo ativo.
- `GET /health/ready`: aplicação e dependências prontas.

O contrato HTTP versionado em `contracts/openapi.yaml` é a fonte técnica de
verdade. O frontend não deve inferir campos ausentes nem reutilizar a última
resposta como se fosse uma leitura nova.

## Restrições confirmadas

- Vue 3, TypeScript e Vite.
- Tailwind CSS com tokens próprios, sem Vuetify.
- Chart.js por `vue-chartjs`.
- `fetch` para REST e WebSocket para eventos; REST recupera o estado ao reconectar.
- Contraste WCAG AA, foco visível e HTML semântico.
- Suporte a redução de movimento.
- Gráfico acompanhado de resumo textual e tooltips acessíveis.
- Cobertura mínima de 80% para a lógica do frontend.

## Sinais de sucesso

- O operador reconhece estado e atualidade em poucos segundos.
- Alterar o DHT22 simulado produz uma mudança coerente no dashboard.
- Os valores atuais correspondem ao resumo retornado pela API.
- O gráfico corresponde ao histórico e ao período selecionado.
- Nenhum estado depende somente de cor.
- Uma falha no histórico não apaga uma leitura atual válida.
- Desktop e mobile permitem completar o mesmo fluxo principal.
- O fluxo completo pode ser demonstrado de forma reproduzível.

## Riscos que o design deve enfrentar

- Aparência decorativa competir com o diagnóstico operacional.
- Cor ser usada como única indicação de criticidade.
- Leitura antiga parecer atual.
- Erro de histórico quebrar todo o dashboard.
- Detalhes técnicos dominarem a experiência do operador.
- O protótipo parecer certificado ou oferecer orientação sanitária.

## Histórico da direção visual

A primeira direção foi definida a partir destas etapas:

1. explorar direções para a superfície operacional;
2. escolher uma composição coerente com “caderno de laboratório encontra
   painel industrial”;
3. aprovar versões desktop e mobile;
4. verificar hierarquia, estados e acessibilidade da composição.

Em 09/09/2026, a CS-26 aprovou a direção **Caderno de bancada**, a composição
**B — Gráfico ampliado**, desktop, mobile e os estados da interface. A revisão
visual e a validação funcional de acessibilidade e responsividade foram
concluídas. As evidências estão vinculadas no
[`README.md`](README.md).

## Redesign de portfólio — setembro de 2026

Direção autorizada: **tecnologia de precisão**. Apresentação escura, com grafite
e ciano; dashboard claro, com acento petróleo. Inter local e números tabulares.
Os temas são fixos por rota, sem alternador.

A apresentação atende visitantes do portfólio e avaliadores. Explica problema,
arquitetura, demonstração gravada e limites acadêmicos. Não consulta a API.
“Ver demonstração” abre a seção de mídia; “Ver código” abre o repositório.
A demonstração usa capturas reais da interface com respostas HTTP simuladas,
identificadas no vídeo e nas imagens. Não oferece sistema real público.

Estado e atualidade permanecem próximos; temperatura dominante, umidade
secundária e histórico amplo. Uma leitura antiga é explicitamente a última
leitura conhecida, sem confirmar a situação atual. Eventos chegam por WebSocket;
REST recupera o estado ao reconectar. Falha do histórico preserva o resumo válido.

Motion for Vue executa entradas uma vez; com redução de movimento, o conteúdo
aparece imediatamente. Medições não têm contadores animados. Vídeo com
controles nativos, legendas descritivas e sem reprodução automática.

Figma, mapa de componentes, dependências, mídia, testes e justificativas:
[Relatório da entrega](../docs/testing/redesign-portfolio.md).
