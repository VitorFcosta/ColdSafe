# Frontend

Esta área receberá o dashboard Vue 3 com a direção **Caderno de bancada** e a
composição **B — Gráfico ampliado**, aprovadas em 09/09/2026 na CS-26.

Não há código visual nesta fase.

A definição confirmada do produto, do público, do escopo e das restrições está
em [`PRODUCT.md`](PRODUCT.md).

Desktop, mobile e os oito estados da interface foram aprovados. O registro das
decisões e as imagens estão na [CS-26 no Notion](https://app.notion.com/3cfd67001da981108554cd452d3191b7).
Os arquivos locais de trabalho do Impeccable ficam em `.impeccable/`, fora do Git.

A composição mantém estado e atualidade juntos, temperatura dominante e histórico
amplo abaixo das métricas. No mobile, as informações são empilhadas. Falha do
histórico preserva a leitura atual válida; leitura antiga aparece como última
leitura conhecida, sem confirmar o estado atual.

O próximo passo é a CS-27: criar Vue, Tailwind e os tokens próprios do ColdSafe.
O conteúdo de `DESIGN.md` está preparado no registro da tarefa para criação local
pelo autor do projeto. Contraste completo, teclado e responsividade serão
validados na implementação; os mockups não substituem esses testes.
