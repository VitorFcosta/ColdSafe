# Consolidação da documentação — 13/10/2026

Pedido de Vitor: documentação principal na pasta do projeto, enxuta e sem
duplicações entre projeto e Notion. O plano aprovado não foi refeito.

## Organização e arquivos

| Papel | Arquivos / motivo |
| --- | --- |
| Entrada para pessoas | `docs/README.md`: encontrar o assunto sem ler tudo |
| Entrada para agentes | `AGENTS.md`: indicar leitura seletiva e registro local |
| Retomada AIoT | `docs/aiot/README.md`: decisões, situação e protocolo únicos |
| Planejamento aprovado | `docs/aiot/plan.md`, `architecture.md`, `requirements.md`, `presentation.md` |
| Execução AIoT | `docs/aiot/tasks/B2-01.md` a `B2-36.md` e índice: um cartão por tarefa |
| Histórico | `docs/history/tasks/`: 76 cartões anteriores e 4 retirados de UX |
| Enunciado e material antigo | `docs/history/assignment.md`, `project-notes.md`, `presentation-2026-09.md`, `design-2026-09.md`, `visual-evidence.md` |
| Evidências de outubro | `docs/evidence/b2-03.json` e `b2-04.json`: dados medidos / hashes e resultados |
| Mídia antiga | `docs/history/media/`: 10 PNGs e um vídeo, diferentes da mídia atual |
| Rastreabilidade | `docs/history/source-map.json`: origem, destino e hashes dos anexos |
| Recuperação | `docs/history/notion-original.zip`: registros originais comprimidos, sem URLs de download temporárias |

Os documentos TDD, runbook, versões e relatórios locais já existentes foram
reaproveitados. O README principal e o contrato AIoT apontam para a documentação
local. Configuração referencia o runbook e a matriz, evitando repetir o bootstrap
e as versões. A cópia antiga do relatório de redesign fica somente no arquivo de
segurança; a versão atual continua em `docs/testing/redesign-portfolio.md`.

Removidos dos cartões: protocolo repetido, prompts de retomada genéricos, regra
revogada de pedir autorização separada para código e indicações antigas de qual
tarefa iniciar. Aceite, dependências, datas, evidências e limitações preservados.
No histórico, instruções e próximos passos antigos não autorizam ações atuais.

Nos 32 cartões AIoT ainda não iniciados, o texto passou de 73.749 para 29.114
caracteres: **60,5% menor**. Isso mede redução de texto, não custo exato de tokens.

## Verificações desta migração

- 112 tarefas nomeadas recuperadas: 36 AIoT e 76 históricas; mais 4 retiradas de UX.
- 15 anexos recuperados. Arquivos copiados têm SHA-256 igual ao original.
- 36 cartões AIoT e 80 históricos/retirados conferidos; nenhum status de tarefa
  foi alterado por esta migração.
- Links locais e referências aos anexos conferidos. Arquivo ZIP íntegro.
- Metadados B2-04 preservam a rodada anterior de 62 testes; esses testes não
  foram reexecutados nem contados como verificação nova da aplicação.
- Sem alteração de aplicação, schemas, testes, firmware, Compose ou dependências.
- Alterações desta sessão são documentais; não houve commit, push ou publicação
  de arquivos no GitHub.

## Checkpoint

Consolidação concluída: **130 páginas do Notion reduzidas a referências locais**
e relidas para confirmar os caminhos e a preservação de 25 blocos de navegação.
Não foram apagadas páginas, tarefas ou bases; os status foram preservados.

Exceção: “Redesign para portfólio — entrega e commit” tem um ancestral na
lixeira. O Notion recusou sua edição por esse motivo. O conteúdo e os anexos
foram recuperados; o item continua como histórico arquivado, sem restaurar
páginas excluídas. A fonte local é `docs/testing/redesign-portfolio.md`, e a
versão anterior está no arquivo de segurança.

Próxima retomada: `docs/README.md`, guia AIoT e apenas a tarefa escolhida.
Não iniciar B2-05 automaticamente. A pasta é a fonte atual; propriedades do
quadro do Notion ficam como registro histórico, sem manutenção duplicada.
