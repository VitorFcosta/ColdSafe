# P-05 — Estratégia do gêmeo digital

**28/10/2026 · aprovada para planejamento · nenhum experimento 3D executado.**
Orientação visual: [G-01 a G-06](../design-system/digital-twin.md).

O usuário confirmou nesta data: a entrega funcional será 3D real no navegador,
com geometria selecionável e dados associados; bitmap é somente referência visual.
Câmera fixa não significa imagem estática. A representação não é simulação física
validada nem medição de RPM. Experimento e integração estão no [roadmap](../tasks/README.md).

## Decisão inicial e evidência

Primeira candidata: refinar a geometria própria no Three.js já instalado,
com câmera fixa em três quartos, materiais grafite acetinados e iluminação
suave. Preservar seleção/ciclo de vida/dados. Não adicionar motor, biblioteca
de interação ou pós-processamento pesado para iniciar o experimento.

[DigitalTwinScene.vue](../../../frontend/src/features/digital-twin/DigitalTwinScene.vue)
já usa câmera ortográfica frontal, primitivas, materiais padrão, luz ambiente/
direcional, seleção por ID e DPR limitado a 2. O grupo giratório atual só tem
cubo/hélices: no refinamento, rotor/hélices precisam ficar separados da grade,
carcaça, sensores e base, que permanecem imóveis.

[twin-state.ts](../../../frontend/src/features/digital-twin/twin-state.ts)
separa estado visual atual e itens autorizados. Reaproveitar nove IDs, lista,
seleção, stale, redução de movimento, aba oculta e descarte. Material compartilhado
não pode fazer a seleção de um item modificar a aparência de outro.

Geometria própria oferece controle do detalhe e associação dos itens, mas não
garante fidelidade fotográfica à imagem. O experimento compara a aparência e o
custo antes de produzir a versão final. Sem câmera manipulável, não apresentar
órbita, zoom ou “Vista inicial”.

## Pausa visual e acessibilidade

Acrescentar “Pausar animação”/“Retomar animação” junto à cena: a rotação ilustrativa
não é essencial para ler os dados, disponíveis também na lista. Essa decisão
aplica o [critério Pause, Stop, Hide do W3C](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)
ao movimento automático que dura mais de cinco segundos junto de outro conteúdo.
É uma especificação nova da P-05, não capacidade já implementada.

A pausa afeta somente o movimento visual, nunca envia comando ao equipamento e
não interrompe consultas, atualização da lista ou indicação de idade da leitura.
Enquanto a vista estiver montada, novas leituras e seleção de peça não desfazem
a pausa manual. Retomar usa a observação atual válida, sem reproduzir dados antigos.
Leitura vencida, aba oculta e movimento reduzido continuam impedindo o loop;
o botão não sobrepõe essas condições. Quando retomar não for possível, exibir
o motivo associado ao controle. Sem preferência global ou armazenamento novo.

Na implementação, verificar teclado, nome/estado anunciado e permanência do foco.
O controle de atualização automática dos demais conteúdos exige avaliação própria
do critério; este botão não comprova conformidade de toda a página.

## Alternativa de asset e origem

Se a geometria própria não alcançar a silhueta/acabamento com esforço aceitável,
avaliar um GLB ou produzir uma malha própria exportável. O
[Three.js recomenda glTF/GLB](https://threejs.org/manual/pages/loading-3d-models.html)
para distribuição de modelos; o [Khronos](https://www.khronos.org/gltf/) descreve
o formato e seus recursos. Isso não implica adoção de um arquivo específico.

Para qualquer asset externo: registrar URL exata, autor, licença/data, arquivo
original e alterações; verificar permissão para incorporar e redistribuir no
projeto. Conferir escala/orientação, rotor separado, malha/texturas e associação
às chaves de inspeção. O asset não conhece os IDs autorizados da telemetria.

[Poly Haven](https://polyhaven.com/license) declara CC0 para seus assets; é uma
opção de pesquisa para materiais/iluminação se necessário. Não foi selecionado
ou baixado modelo/HDRI/textura. Licença de asset não é licença de toda a página
ou de imagens promocionais do site. Nenhum asset pago ou conta externa foi usado.

## Experimento futuro, antes da produção completa

Executar somente em uma tarefa de implementação autorizada. Comparar cena atual
e candidata com o mesmo equipamento/dados/estados, em desktop e celular reais
identificados; registrar hardware, SO, navegador, viewport, DPR, build e condições.
Medir por 60 s após aquecimento, com movimento ativo e também em estados inativos.

| Medida | Meta inicial proposta — não resultado medido |
| --- | --- |
| Geometria visível | Até 50 mil triângulos. |
| Chamadas por quadro | Até 100, contando passes adicionais. |
| Resolução | DPR máximo 2; avaliar 1,5 no celular se necessário. |
| Asset adicional, se houver GLB | Até 3 MB transferidos; texturas inicialmente até 1024 × 1024. |
| Movimento ativo | Pelo menos 30 FPS médios e p95 do intervalo entre quadros até 40 ms. |
| Seleção de item | Feedback visual/lista em até 100 ms no cenário de referência. |
| Ciclo de vida | Dez montagens/desmontagens sem crescimento progressivo atribuível à cena. |
| Inatividade | Sem loop contínuo com pausa manual, cena parada, leitura vencida, aba oculta ou movimento reduzido; render pontual de seleção/redimensionamento quando necessário. |

São alvos locais a revisar com evidência, não padrões universais ou garantias
para todo dispositivo. Se falhar: simplificar malha, resolução, sombras e rótulos;
comparar de novo antes de acrescentar dependências. Se o acabamento ficar abaixo
da referência, registrar diferença e decidir com o usuário, sem fingir equivalência.

Contagens de `renderer.info` ajudam a acompanhar chamadas/recursos, mas não são
bytes exatos de GPU. Não exigir zero absoluto ao desmontar: comparar a evolução
por ciclos e o que pertence à cena.
[WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html).
Geometrias, materiais e texturas exigem descarte conforme responsabilidades de
propriedade; loaders podem introduzir recursos adicionais.
[Cleanup](https://threejs.org/manual/pages/cleanup.html).

O aceite funcional inclui: nove itens por ID, troca de equipamento/conta, lista
por teclado, contraste/legibilidade dos rótulos, LED/ACK separado da observação,
sem comando por seleção, série contextual identificada, stale, WebGL indisponível,
pausa manual, redução de movimento e cleanup. Nenhum desses testes foi executado nesta P-05.

## Ilustração usada nas composições

[Equipamento conceitual P-05](../assets/compositions/equipamento-conceitual-p05.png)
é um bitmap novo, derivado da [imagem aprovada](../assets/gemeo-digital-conceito.png)
pela ferramenta integrada **image_gen**, com a skill imagegen. Geração em
28/10/2026, sem CLI/API externa ou dependência adicionada; original preservado e
cópia local sem alteração de pixels. Não é modelo 3D, fotografia do hardware ou
desenho técnico. Número/posição dos volumes ilustrados não define o inventário.

Arquivo de origem: `exec-bbd2700d-4dda-4745-bb6f-33450e2abac7.png`, em
`~/.codex/generated_images/01a179c2-d5a6-79d1-a991-67e6f65da7d7/`.

### Prompt final usado

```text
Use case: precise-object-edit. Asset type: static product illustration for ColdSafe digital-twin planning mockups. Input image: the approved ColdSafe dashboard screenshot, used as the visual reference for its central industrial desk fan and instrumented base. Primary request: recreate ONLY that central equipment illustration as a standalone landscape studio render, removing the entire UI, sidebar, metrics, chart, texts, labels, numbered pins and leader lines. Keep the same visual identity and three-quarter front view of the dark satin-metal fan, wire safety guard, blades, motor, low rectangular metal base and small sensor housings around/on the equipment. Include the illustrative six sensor housings, one small yellow illuminated LED and one small black buzzer; do not add instruments or extra equipment. Preserve the restrained, realistic industrial materials and recognizable silhouette from the reference. Scene/background: very light neutral gray close to #f3f6f5 with soft contact shadow. Composition: whole equipment visible, centered, comfortable margin, landscape approximately 3:2. Soft studio lighting, crisp silhouette, controlled reflections, no excessive chrome, no dramatic glow. This is an illustrative concept, not an engineering diagram. Text: none. No UI, no words, no badges, no numbers, no arrows, no logos, no watermark. Opaque background.
```
