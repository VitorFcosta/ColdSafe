# ColdSafe — definição do produto frontend

## Propósito

O frontend do ColdSafe é um dashboard operacional acadêmico para reconhecer,
em poucos segundos, o estado de um único ambiente refrigerado simulado, a
atualidade da última leitura e a variação recente da temperatura.

O dashboard também serve como prova visível da cadeia DHT22 → ESP32 → MQTT →
FastAPI → InfluxDB → API → Vue.

> O ColdSafe é um protótipo acadêmico. Ele não é equipamento médico, sistema
> sanitário certificado nem substitui procedimentos oficiais de controle.

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

## Escopo do primeiro bimestre

- Um ambiente: `Laboratório Refrigerado`.
- Um dispositivo: `esp32-lab-01`.
- Dashboard único, sem páginas futuras vazias.
- Temperatura, umidade, horário da leitura, estado e freshness.
- Histórico de temperatura nos períodos `15m`, `1h`, `6h` e `24h`.
- Atualização por polling a cada 5 segundos.
- Estados explícitos de carregamento, ausência de dados, operação normal,
  atenção, criticidade, leitura desatualizada e erro de serviço.
- Falha parcial: se o histórico falhar, a leitura atual válida permanece visível.
- Diagnóstico técnico recolhível para apoiar a demonstração.
- Layout responsivo para desktop e mobile.
- Informação compreensível sem depender apenas de cor.

## Fora do MVP

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
- `fetch` e composables para polling.
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

## Gate antes da implementação visual

Este documento não define paleta, tipografia, componentes ou composição final.
A implementação visual só começa depois de:

1. explorar direções para a superfície operacional;
2. escolher uma composição coerente com “caderno de laboratório encontra
   painel industrial”;
3. aprovar versões desktop e mobile;
4. verificar hierarquia, estados e acessibilidade da composição.

Em 09/09/2026, a CS-26 aprovou a direção **Caderno de bancada**, a composição
**B — Gráfico ampliado**, desktop, mobile e os estados da interface. A revisão
visual foi concluída; a validação funcional de acessibilidade e responsividade
permanece para a implementação. As evidências estão vinculadas no
[`README.md`](README.md).
