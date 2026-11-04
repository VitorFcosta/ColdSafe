# P-05 — Especificação das composições

**28/10/2026 · aprovada para planejamento.** [Pranchas e PDF](README.md).
Os fluxos/contratos completos continuam na [P-01](../inventory.md),
[P-02](../information-architecture.md) e [P-03](../path-evaluation.md).
Esta especificação determina ordem, hierarquia e conteúdo fora do enquadramento;
não substitui contratos por valores fictícios das imagens.

## Regras comuns

Aplicar F/C/G do [design system aprovado](../design-system/README.md). Global
por área, local por vista; título/foco de página, nomes completos, indicação ativa
além da cor e utilitários estáveis. No celular, seletores operacionais ficam
empilhados; nomes locais quebram em linhas. Cabeçalho não cobre o conteúdo/foco.

Os parâmetros de contexto, aviso de rascunho e retomada são mudanças futuras da
P-03, não funções já entregues. Durante consulta de identidade, mostrar estado
ocupado sem conteúdo privado. Expiração/revogação limpam o que deixou de ser
permitido, independentemente de diálogo ou resposta atrasada.

Cada bloco de dados possui seus estados pertinentes: carregamento, vazio,
desatualizado, erro, restrição e recuperação. Falha parcial só é independente
quando a consulta atual a permite; dispositivos/regras da Gestão têm carga
conjunta. Atualização automática não muda foco, seleção ou rascunho.

## M-01 — Apresentação `/`

- **Desktop:** marca e âncoras → propósito/cópia candidata + ilustração → ações
  de demonstração/código → cadeia de aquisição/processamento/visualização.
- **Celular:** mesma narrativa em coluna; ações antes da ilustração; mídia não
  exige arraste ou autoplay. Acesso ao painel preserva o fluxo de autenticação.
- **Continuação obrigatória:** funcionamento/arquitetura, demonstração gravada
  com controles/legendas, contexto acadêmico, limites e rodapé. O hero não substitui
  o conteúdo existente, nem a ilustração substitui a demonstração real gravada.
- **Estados desenhados:** vídeo indisponível com recuperação; movimento reduzido.
  A página permanece independente de API operacional.
- **Limite:** cópia nova é proposta editorial. Conferir coerência com o estágio
  atual do protótipo; nenhum desempenho, certificação ou disponibilidade pública
  é prometido. Render do ventilador explicitamente ilustrativo.

## M-02 — Entrada/cadastro `/login`

- **Desktop:** área de identidade e formulário curto, com retorno à apresentação.
  **Celular:** marca, retorno, título, e-mail, senha, ação e alternância.
- Modo Criar conta mantém exatamente e-mail/senha; botão e orientação mudam na
  mesma rota. E-mail até 254, senha até 128; cadastro exige mínimo de 8 caracteres.
- **Estados desenhados:** erro de acesso e variante de cadastro. Incluir envio
  ocupado e erros associados na implementação; conservar destino interno validado.
- Sem nome adicional, confirmar senha, login social, papel, “lembrar-me” ou
  recuperação de senha. Viewport curto permite rolar sem recortar a ação.

## M-03 — Visão geral `/dashboard`

- **Desktop:** contexto/atualidade → vistas locais → seis grandezas → seletor de
  grandeza e períodos → histórico ao lado da previsão → alertas/comparação e LED.
- **Celular:** contexto → local → grandezas em duas colunas → histórico; controles
  de grandeza/período permanecem no grupo do histórico, podendo continuar após
  o primeiro enquadramento. Em seguida: resumo/tabela, previsão, alertas/comparação
  e atuadores. Rolagem não remove capacidades.
- **Preservar:** 15 min, 1 h, 6 h e 24 h; unidade correta; resumo, fuso, cobertura
  e tabela; limites térmicos atuais somente quando pertinentes; valores ausentes
  não viram zero. A posição final dos controles deve ser conferida com texto ampliado.
- **Estados desenhados:** leitura antiga e falha do histórico mantendo leitura
  atual válida. Previsão vencida oculta números conforme contrato e não encerra
  alerta persistido por inferência.
- **LED:** observação com idade separada do pedido. Envio/pendência/rejeição/sem
  confirmação continuam; navegação ou seleção não repetem comando. Viewer consulta.

## M-04 — Saúde e previsões `/insights`

- **Desktop:** contexto → estimativas/origem → tendência e alertas → regras.
  **Celular:** mesmas seções em coluna; informação temporal permanece próxima
  da estimativa, sem transformar temperatura normal em diagnóstico global.
- **Regras completas:** saúde crítica/recuperação, RUL crítica/recuperação e
  contagens para abrir/encerrar. Os seis valores da prancha são exemplos, não
  novos defaults. Estado de consulta para viewer; edição só conforme papel atual.
- **Continuação:** detalhes temporais, versão, eventos persistidos e explicações
  dos limiares. Preservar rascunho no polling; validar relação entre limiares ao salvar.
- **Estados desenhados:** ausência/warm-up de previsão e alterações não salvas.
  Falhas específicas continuam nomeadas; não resumir todas como “sem modelo”.

## M-05 — Gêmeo `/digital-twin`

- **Desktop:** contexto/local → faixa de grandezas → cena em três quartos ao
  lado da lista → detalhe/histórico de 15 min e previsão associada. Item selecionado
  permanece reconhecível na lista; nove itens continuam acessíveis mesmo quando
  apenas parte da lista couber no enquadramento inicial.
- **Celular:** contexto/local → cena → última leitura selecionada → acesso à
  lista → nove itens → detalhe/histórico e previsão. O link para componentes é
  deslocamento interno; não cria outra rota nem depende de a imagem carregar.
- **Detalhe completo:** nome/ID, leitura, unidade, idade/horário, série correta,
  indicação de série contextual para itens sem histórico próprio e LED quando
  aplicável. Previsão de equipamento separada de sensor/atuador, que não possui RUL.
- **Estados desenhados:** falha gráfica com lista preservada e leitura antiga
  com movimento congelado. Legado explica requisito AIoT sem criar cena fictícia.
- **Decisão P-05:** câmera fixa, sem arraste/órbita/zoom na primeira candidata.
  Nenhum botão “Vista inicial” é mostrado sem manipulação real. Refinamento visual
  e experimento descritos em [estratégia 3D](3d-strategy.md).
- **Controle visual:** “Pausar animação”/“Retomar animação” junto à cena, por
  teclado e toque. Pausa local do movimento, sem comando físico; dados e lista
  continuam atualizados. Retomar respeita leitura válida, aba visível e preferência
  de movimento reduzido. Ver contrato e estados na estratégia 3D.

## M-06 — Gestão `/manage`

- **Desktop:** ambientes à esquerda; dispositivos e limites à direita, com
  formulários junto do objeto. **Celular:** ambiente → dispositivos → limites.
- **Campos:** ambiente/nome do dispositivo até 120 caracteres; MQTT ID até 64,
  alfanumérico/ponto/sublinhado/hífen e imutável depois de criado. Limites: mínimo,
  máximo e margem não negativa menor que metade da faixa.
- **Continuação:** formulário de adicionar/renomear ambiente, adicionar/editar
  dispositivo, ajuda/validação dos limites e confirmação de desativação.
- **Estados desenhados:** vazio para viewer e confirmação com Cancelar/Desativar
  dispositivo. Identificar objeto, foco inicial seguro e retorno de foco.
- Sem exclusão definitiva, reativação, mover dispositivo ou editar MQTT ID.
  Seleção própria da Gestão, conforme P-02. Erro da carga conjunta não deve
  aparentar que uma metade foi confirmada independentemente.

## M-07 — Filas e mensagens `/messaging`

- **Desktop:** propósito/idade → métricas globais → filas → amostras privadas e
  cópias da DLQ. **Celular:** mesmas seções; tabelas com região de rolagem nomeada
  quando necessário. Sem seletor operacional de equipamento.
- **Continuação:** contagens/taxas/consumidores completos, amostras/motivos/origem,
  observador e atualização. Nomes/valores da prancha são exemplos, não broker consultado.
- **Estados desenhados:** observador desatualizado e acesso restrito. Separar
  atualidade do observador da idade de coleta das métricas.
- Amostras privadas, efêmeras, até 100 eventos e 100 cópias DLQ; não são histórico
  durável. Sem corpos brutos, purga, reentrega ou controles Docker.

## M-08 — Dados sintéticos `/laboratory`

- **Desktop:** configuração agrupada à esquerda; estimativa, estado do LLM e
  retomada conhecida à direita. **Celular:** informação de escopo/LLM → parâmetros
  → sensores/falhas/operação → estimativa → Gerar dataset → acompanhamento/resultado.
- **Configuração completa:** linhas, seed, equipamentos, dias, fração com falha,
  ruído, faltantes, outliers; ambiente é UUID opcional em texto livre. Sensores
  (seis), falhas (desgaste/desbalanceamento), operação (normal/pesada/cíclica).
  Pelo menos uma opção em cada conjunto, conforme validação existente.
- **Limites atuais a preservar:** linhas de 1.000.000 a 2.000.000, equipamentos 1–10.000,
  seed inteira 0–4.294.967.295, dias >0 até 3.650, frações 0–1, ruído 0–10.
  Defaults ilustrados coincidem com a base conferida; não alteram o contrato.
- **Resultado/continuação:** identificação/etapa/progresso do job, configuração
  enviada, qualidade por sensor, faltantes/min/máx, RUL observada/censurada, taxa
  de outliers configurada, amostra determinística de até 10 linhas e limites.
- **Estados desenhados:** envio incerto sem repetição automática e execução em
  andamento. 100% não confirma conclusão. Link para treinar só após dataset concluído.
  Sem upload, exportação ou cancelamento remoto acrescentados.
- Retomar aparece nas duas vistas de Dados e modelos apenas para referências
  conhecidas da aba e autorizadas; detalhes de sessão/GET seguem A-01 da P-03.

## M-09 — Treinamento `/training`

- **Desktop:** dataset/configuração → acompanhamento → aptidão e resultados
  de saúde/RUL. **Celular:** mesma sequência empilhada, diagnósticos por alvo.
- Lista dos 50 datasets próprios concluídos mais recentes; URL pode trazer outro
  dataset autorizado. Mínimo de três equipamentos; seed de treino/split 42 e
  divisão aproximadamente 70%/15%/restante por equipamento não são editáveis.
- **Continuação obrigatória:** validação/teste, MAE/RMSE/R² do candidato e baseline,
  previsto × real, tabela de erros, importância por permutação, proximidade da
  falha quando disponível, versões e limitações. Diagnósticos usam até 500 linhas
  do teste. Não reduzir o resultado às seis métricas da imagem.
- **Estados desenhados:** job concluído/pacote rejeitado e resultado indisponível
  recuperável por GET. Modelo não é ativado pela conclusão. Retomada conhecida
  não inicia treino; botão de envio permanece explicitamente diferente.
- Sem seletor de algoritmo, hiperparâmetros ou ativação visual de modelo.

## M-10 — Assistente `/assistant`

- **Desktop:** estado/escopo → conversa e sugestões → pergunta/limites/ação.
  **Celular:** conversa e pergunta em coluna; sugestões acessíveis na continuação.
- Seis sugestões: Estado atual, Pior equipamento, Vida útil restante, Significado
  dos alertas, Métricas do modelo, Arquitetura; só preenchem. Limite de 256 bytes
  UTF-8 e 5 perguntas/minuto. Até oito perguntas locais, cada envio independente.
- **Continuação:** limites, sugestões e link para conferir em Saúde e previsões.
  Não presumir que a pergunta se limita ao equipamento selecionado em outra vista.
- **Estados desenhados:** runtime indisponível e resposta incompleta. Durante
  streaming: texto progressivo, envio ocupado e Cancelar resposta. Anunciar início,
  conclusão/interrupção/erro sem reler todo fragmento; foco permanece com a pessoa.
- Sair da página/trocar sessão apaga conversa. Sem anexos, voz, memória permanente
  ou comando remoto. Texto recebido não vira HTML.

## S-01 — Estados transversais e foco

Quatro amostras em 320 px: menu aberto, rascunho antes de sair, link indisponível
e verificação de identidade. São intenções de comportamento a testar depois.

- Menu modal: nome acessível, fundo inerte à interação/leitura assistiva, foco
  contido, Fechar/Escape e retorno; selecionar destino fecha e orienta a nova página.
- Rascunho: permanecer conserva valores/contexto; descartar efetiva uma transição.
  Logout/revogação não ficam bloqueados por esse aviso.
- URL inválida/inacessível: explicar sem revelar recursos de terceiros; escolha
  autorizada, sem trocar silenciosamente para o primeiro equipamento.
- Identidade pendente: não mostrar dados privados nem classificar papel como viewer.
  Falha de consulta oferece nova verificação; não representa revogação confirmada.

## Verificação futura delimitada

Na implementação: usar cenários P-03 e testes existentes por família; validar
320 px/reflow/texto ampliado, teclado/ordem de foco, papéis, troca de conta,
URL/voltar/recarga, dados vencidos/ausentes e falhas por seção. O presente trabalho
não executa essas interações e não mede descoberta por pessoas.
