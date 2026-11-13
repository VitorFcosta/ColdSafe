# Empacotamento e origem das imagens — 05/11/2026

Concluído: cópias de runtime menores e identificação Git nativa nas nove imagens
da aplicação. Os nove containers foram recriados sem iniciar os serviços;
os 16 containers pessoais continuam parados. Os modos de execução não mudaram.

## O que mudou

- `.dockerignore`: testes do backend deixam de entrar no contexto de construção.
- `backend/Dockerfile`: copia explicitamente o pacote backend, módulos compartilhados,
  schemas e as 12 migrações SQL. Testes, documentação, exemplos de contratos e
  arquivos de desenvolvimento deixam de acompanhar a aplicação.
- `gateway/Dockerfile` e `writer/Dockerfile`: copiam seus módulos Python em vez
  das pastas inteiras, evitando README/Dockerfile no pacote de execução.
- `docs/runbook.md`: ativa e explica `BUILDX_GIT_LABELS=full` e
  `BUILDX_GIT_CHECK_DIRTY=1` no macOS/Linux e PowerShell, além da inspeção e testes.
- `backend/tests/infra/test_application_images.py`: três verificações opcionais
  sobre imagens construídas, usando somente a biblioteca padrão do Python.

Não há script de build novo, dependência nova, atualização de versões ou alteração
dos arquivos Compose, limites de RAM/CPU, credenciais, redes ou volumes pessoais.

## Origem registrada

Todas as nove imagens registram o repositório do ColdSafe e a revisão
`62cb4cca651a00d74e8b1d627607013637e5ba30-dirty`.
O sufixo é necessário porque os Dockerfiles e o runbook ainda têm alterações
locais não commitadas. Isso não equivale a um commit novo, assinatura ou hash
completo da árvore de trabalho. Para repetir os rótulos em builds futuros, use
as variáveis no terminal, conforme o runbook; elas não são uma configuração
global permanente nem são passadas ao ambiente de execução dos serviços.

Fonte: [variáveis Git do Docker Buildx](https://docs.docker.com/build/building/variables/#buildx_git_labels).

## Medição de tamanho

Comparação do mesmo campo `docker image inspect .Size`, em bytes:

| Imagem | Antes | Depois | Redução reportada |
| --- | ---: | ---: | ---: |
| backend | 142.046.903 | 141.745.553 | 301.350 |
| gateway | 55.966.503 | 55.962.968 | 3.535 |
| writer | 61.643.687 | 61.640.016 | 3.671 |

O backend e cada uma de suas quatro imagens de workers apresentaram cerca de
294 KiB a menos nesse indicador, aproximadamente 0,21%. Não somar esses valores
como espaço físico liberado: as imagens compartilham camadas. Esse campo também
não mede RAM, espaço livre no host ou necessariamente o tamanho exibido pelo
Docker para o filesystem de um container. Simulator e frontend mantiveram seu
conteúdo de runtime; os metadados acrescentaram respectivamente 225 e 58 bytes
ao mesmo indicador. A redução é pequena; o ganho principal é um pacote de
execução mais limpo e uma origem verificável por inspeção.

## Verificações executadas

1. Antes das construções, três testes: runtime/assets passaram; ocorreram 12
   falhas em subtestes, correspondentes aos nove rótulos e às três imagens com
   testes/documentação.
2. Nove builds sequenciais passaram, com dependências existentes em cache.
3. Três testes das imagens passaram: módulos de entrada e workers importáveis,
   hashes dos módulos/schemas/migrações iguais ao checkout, ausência de testes
   e documentação no runtime e rótulos das nove imagens corretos.
4. Trinta testes existentes de contrato Compose/imagens dos brokers passaram.
   A seleção focada foi executada sem plugins automáticos e sem os argumentos
   globais de cobertura; não representa medição da cobertura total do backend.
5. Os nove containers da aplicação apontam para as imagens construídas. Mesmo
   conjunto de 16 serviços, montagens, permissões, configuração e limites de CPU/RAM.
6. Mesmo conjunto e metadados dos 222 volumes existentes no engine; esse total
   inclui outros projetos/testes, não apenas os volumes do ColdSafe pessoal.
7. `.env`, arquivos de `simulator/local` e os três arquivos da evidência anterior
   `docker-refresh-2026-11-05` conservaram seus hashes. Conteúdos pessoais não
   foram copiados para esta evidência.
8. Zero partidas dos serviços pessoais. Os testes criaram containers temporários
   sem rede, sem volumes pessoais e sem executar servidores, inferência, geração,
   treinamento ou carga de modelos; todos foram removidos. A auditoria distingue
   essas execuções das partidas da aplicação. A repetição GREEN após separar
   os rótulos Compose dos testes também passou.

9. Revisão independente: nenhum problema material no escopo alterado.

Comandos reproduzíveis e limites dos testes estão no runbook. O
[`report.json`](report.json) conserva identidades e verificações com o e-mail
do campo `maintainer` omitido. Os logs brutos foram arquivados fora do repositório.

## Limites e próxima ação

Condição observada: Mac M1 de 8 GB, fora da tomada e com aplicativos pessoais
preservados. Pressão de memória em alerta nas capturas imediatamente antes e
depois da operação, sem atribuição causal isolada. Não houve mudança no modo de
energia ou nos limites da VM/containers, nem teste do assistente Metal.

Não foi medida economia de RAM, tempo de inferência, desempenho em Windows ou
funcionamento integrado da pilha. Os testes importam módulos, mas não iniciam
servidores/consumidores nem leem ou comparam byte a byte os bancos, datasets e
modelos pessoais. A preservação verificada é das montagens, identidades e arquivos
locais protegidos; os serviços que escrevem nos volumes permaneceram parados.

Próxima ação: usuário escolhe revisão/commit ou outro trabalho. Não iniciar modos
de execução, alterar limites ou avançar o roadmap automaticamente.
