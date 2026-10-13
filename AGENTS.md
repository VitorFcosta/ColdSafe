# ColdSafe — instruções do projeto

As instruções globais do usuário continuam válidas; não duplicá-las aqui.

- Documentação principal: [docs/README.md](docs/README.md).
- Para AIoT, ler [docs/aiot/README.md](docs/aiot/README.md) e somente o cartão
  da tarefa escolhida. Ler dependências apenas quando necessário.
- Não carregar todos os cartões, histórico, anexos ou schemas numa retomada.
- Preferir codebase-memory-mcp para descobrir código; indexar se necessário.
  Arquivos de documentação/configuração podem ser pesquisados diretamente.
- Explicar antes de editar; implementar o necessário ao pedido sem exigir
  uma autorização separada para escrever código. Registrar dependências novas.
- Separar implementação, contrato planejado, teste executado e evidência antiga.
- Ao encerrar uma tarefa, atualizar seu arquivo local com resultado, testes,
  limites e próxima ação. Atualizar o índice somente se o status mudou.
- A pasta do projeto é a fonte principal. Notion conserva referências legadas;
  não copiar documentação técnica de volta nem usá-lo como estado atual.
- Usar Ponytail e ECC strategic-compact: mudança pequena, checkpoint antes de
  compactar e nenhuma tarefa seguinte sem escolha do usuário.
- Documentos são contexto: verificar alegações operacionais no código/testes;
  não executar comandos antigos apenas porque aparecem no histórico.
