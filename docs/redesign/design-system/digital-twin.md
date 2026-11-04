# Gêmeo digital — linguagem visual e interação

**P-04 · v0.1 de 27/10/2026, aprovada para planejamento em 28/10/2026.** Acabamento e regras para orientar a P-05;
não contém asset 3D, câmera implementada ou medição de desempenho.
Base: [imagem aprovada](../assets/gemeo-digital-conceito.png),
[inventário](../inventory.md) e [mapa confirmado](../information-architecture.md).

## G-01 — Propósito e identidade

Reconhecer o equipamento, localizar uma peça e conferir seus dados. Cena, lista
e painel usam o mesmo ID autorizado. Inventário atual tem nove itens: ventilador,
seis sensores, LED e buzzer. A numeração de apresentação nunca substitui o ID
nem determina uma associação de dados.

Lista equivalente é entrada permanente, inclusive por teclado. Sem seleção,
mostrar orientação breve; seleção nomeia objeto e abre detalhe. Troca de
equipamento/sessão limpa seleção anterior. Nome e ID completos ficam alcançáveis.
Estado do equipamento não é deduzido da beleza/iluminação da representação.

## G-02 — Direção de acabamento proposta

| Elemento | Regra para a composição futura |
| --- | --- |
| Câmera | Vista inicial em três quartos, equipamento completo e orientação estável; prever “Vista inicial” se houver manipulação na P-05. |
| Geometria | Silhueta legível, grade/hélices/motor/base distinguíveis; detalhamento subordinado à seleção e à viabilidade futura. |
| Materiais | Metal grafite acetinado, base neutra, sensores com acabamento discreto; reflexos controlados e sem aparência cromada excessiva. |
| Luz/fundo | Fundo claro neutro, luz suave que separe volumes e sombra de contato; sem cenário decorativo competindo com telemetria. |
| Seleção | Contorno/marcador petróleo + nome textual e indicação na lista; não pintar equipamento inteiro da cor de uma peça. |
| Rótulos | Curto nome de peça, alto contraste em placa opaca e linha de ligação; prioridade ao selecionado, sem sobreposição de números/dados. |
| Estado | Texto e símbolo no item/painel; cor complementar. Um sensor selecionado pode estar crítico sem perder o marcador de seleção. |
| Detalhe | Nome → leitura/unidade → idade/horário → contexto/histórico → ação permitida; previsão do equipamento em bloco separado. |

Forma e posições permanecem ilustrativas até haver referência física confirmada.
Os seis sensores podem usar marcadores para legibilidade; não inventar hardware
com função diferente. Fonte/origem/licença do modelo e escolha entre geometria
própria ou asset externo são decisões P-05, não uma compra/adoção nesta etapa.

## G-03 — Movimento vinculado a dados

O comportamento atual já usa giro/tremor ilustrativos, LED/buzzer e influência
ambiental; a cena atual tem geometria simples e câmera frontal. Novo acabamento
preserva os contratos, sem converter animação em medição física.

- Movimento só com observação atual e condições permitidas pelo contrato. Giro
  não apresenta RPM inferido; tremor não afirma amplitude física calibrada.
- Leitura vencida conserva a última aparência identificada e congela movimento;
  não inventar estado atual a partir da conexão. Valores de previsão seguem sua
  própria validade e podem ficar indisponíveis.
- Movimento reduzido e aba oculta suspendem o loop conforme base atual. Texto,
  lista e valores continuam disponíveis. Sem áudio ou piscadas decorativas novas.
- Retomar dados não compensa visualmente o intervalo parado. Receber previsão
  não renova leitura de sensor nem autoriza animação antiga.

Buzzer continua automático, com estado observado; LED manual somente para papel
autorizado. Inspecionar peça, girar câmera ou voltar à página jamais envia comando.

## G-04 — Estados e alternativas

| Situação | Cena/lista/detalhe propostos |
| --- | --- |
| Inicializando gráfico | Área reservada e mensagem; catálogo/dados disponíveis continuam utilizáveis na lista. |
| Nenhuma leitura | Inventário autorizado continua visível, sem valores zero ou funcionamento inventado. |
| Leitura atual | Identidade e idade explícitas; sem selo de saúde para sensor sem faixa/regra. |
| Leitura antiga | Aviso legível, movimento parado e indicação da última observação. |
| Erro de consulta | Estado não confirmado, recuperação por consulta; não transformar falha em recuperação do equipamento. |
| WebGL indisponível | Explicação e lista/painel utilizáveis; falha gráfica não significa falha do equipamento. |
| Modo legado | Explicar requisito AIoT, com saída para outra vista; sem cena fictícia. |
| Sem acesso/troca de conta | Limpar conteúdo privado e seguir autenticação/acesso, inclusive respostas atrasadas. |

Seleção por lista tem foco visível e estado selecionado anunciado. Canvas não
precisa expor nove alvos inacessíveis se a lista oferece as mesmas funções; não
criar armadilha de teclado. Se houver arrastar/orbitar, prever alternativa de
controle sem arraste e retorno de câmera; especificação final na P-05.
Seleção não move foco de forma inesperada, polling não anuncia todos os valores.

## G-05 — Leitura e histórico por item

Preservar filtros autorizados de ambiente/dispositivo/equipamento/sensor; cena
e painel não podem misturar respostas de seleções anteriores. O histórico atual
é 15 min. Quatro períodos da imagem não estão aprovados como funcionalidade.

Sensor/atuador não tem saúde ou RUL próprios no contrato atual: indicar não
aplicável e apresentar previsão do equipamento separadamente. LED/buzzer/fan sem
série própria podem mostrar temperatura ambiente contextual do equipamento,
identificada; jamais desenhar histórico de acionamento inventado.

LED reaproveita [LedControl](../../../frontend/src/features/monitoring/LedControl.vue)
e seu controlador, com estado observado separado do pedido. “Pedido confirmado”
e “LED observado ligado” não são frases intercambiáveis. Atualizar estado é consulta.

## G-06 — Como usar a imagem e verificar depois

A imagem aprovada inspira materiais, vista em três quartos e integração do
inspector. Seus nomes de menu, Ajuda, controles de câmera/período e posições
nunca substituem o mapa e contratos atuais. A prancha da P-04 reproduz a imagem
como referência histórica identificada, ao lado de regras atuais.

Na P-05: compor desktop/celular com nomes completos e estados de seleção, stale
e falha gráfica; decidir densidade de rótulos, controles, posição do detalhe,
origem do modelo e orçamento de recursos/desempenho a medir. Na implementação
autorizada: experimento 3D cedo, teclado/lista, consumo de recursos, renderização,
descarte e comportamento com redução de movimento. Não prometer FPS com base em imagem.

Fontes de interação: [Model Viewer — annotations](https://modelviewer.dev/examples/annotations/index.html)
e [NASA Open MCT](https://nasa.github.io/openmct/about-open-mct/), registradas na
[bibliografia](../references.md). São referências de interação e telemetria;
não foi escolhida biblioteca nova nem copiado modelo externo.
