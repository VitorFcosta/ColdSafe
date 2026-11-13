# Inicialização padrão completa

Alteração iniciada em 05/11/2026 e verificada novamente em 08/11/2026.

Na raiz do checkout com o comissionamento concluído, `docker compose up`
seleciona os 14 serviços persistentes e os dois inicializadores da entrega.
`docker compose up -d` usa a mesma composição em segundo plano.

O novo `compose.override.yaml` reúne as definições já usadas pelo comando
completo anterior. O Compose carrega esse arquivo junto de `compose.yaml`
por descoberta padrão. [Documentação do Docker](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/).

O comissionamento da primeira instalação usa `-f compose.yaml` para preparar
os bancos e cadastrar o proprietário antes de configurar o catálogo. A preparação
dos pesos continua sendo uma ação explícita pelo perfil `llm-setup`.

## Verificações

- `docker compose config --quiet` aceitou a configuração local. A lista de
  serviços do comando padrão contém os 16 esperados.
- A configuração resolvida foi comparada com a composição anterior de cinco
  arquivos, tanto na partida padrão como com `llm-setup`. A comparação conferiu
  comandos, dependências, healthchecks, limites, montagens, redes e permissões.
  Foram normalizados os perfis e a ordem das montagens por destino.
- Quatro testes novos cobrem a descoberta automática, a equivalência da
  composição, a base de comissionamento e a preparação explícita dos pesos.
  A seleção final teve 59 testes aprovados com Docker Compose v5.1.0.
- Os 16 containers foram encontrados parados, com identidades, imagens,
  montagens e limites iguais aos da captura inicial. Os 15 arquivos protegidos
  conservaram seus hashes, incluindo `.env`, catálogo local e evidências anteriores.

Os valores resolvidos de ambiente ficaram em memória durante a comparação.
`checks.json` guarda os resultados. O log bruto foi arquivado fora do repositório.
Dependências adicionadas — zero.

## Limites

A validação foi de configuração e contratos. A partida completa, os healthchecks
em execução e a capacidade no Mac ou no Windows de 8 GB ficam pendentes de ensaio.
O runtime de entrega é o Ollama em CPU dentro do Compose. A etapa de Metal segue
no roadmap próprio.
