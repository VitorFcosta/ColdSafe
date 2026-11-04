# RD-16 — Evidências de entrada e cadastro

Capturas da implementação em **31/10/2026**, usando o cliente/roteador/sessão de
produção com respostas HTTP controladas por Playwright. Os endereços, credenciais
e tokens são fixtures fictícias. Não comprovam integração com o backend real.
A [composição M-02](../compositions/02-acesso.png) permanece referência de design.

| Evidência | Escopo |
| --- | --- |
| [Desktop](desktop.png) / [cadastro com erro](desktop-register-error.png) | 1440 × 1024, texto 100%. |
| [Celular](mobile.png) / [cadastro com erro](mobile-register-error.png) | 390 × 844, texto 100%. |
| [320 px](mobile-320-text-200.png) / [cadastro com erro](mobile-320-text-200-register-error.png) | Viewport 320 × 480, texto 200%, página inteira rolável. |
| [Erro de login](login-error.png) | 1280 × 720; credenciais rejeitadas, campos conservados. |
| [Cadastro ocupado](register-busy.png) | 1280 × 720; pedido retido pela fixture, sem duplicação. |
| [Desktop JSON](desktop.json), [celular JSON](mobile.json), [320 px JSON](mobile-320-text-200.json) | Viewports, versão Chromium e estilos computados da variante cadastro/erro. |
| [Contraste](contrast.json) | 39 pares: 11 textos + borda + foco por viewport; texto mínimo 5,17:1. |

Todos os PNGs foram abertos e conferidos; não são mockups. MacOS 27.0.1 arm64,
Node 24.22.1 do runtime local, Chromium 153.0.8010.12, movimento reduzido.
Textos, foco visível, ordem de teclado, alvo mínimo de 44 px, validação nativa,
ausência de overflow e alcance por rolagem possuem verificações no
[spec E2E](../../../../frontend/e2e/access-redesign.spec.ts).
A altura de 360 px no teste adicional representa espaço reduzido; não reproduz
um teclado virtual real. Sem aparelho móvel físico ou leitor de tela.

O [checkpoint RD-16](../../tasks/RD-16.md) registra comandos, resultados e limites.
