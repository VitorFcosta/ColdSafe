<script setup lang="ts">
import { computed } from 'vue'
import { motion, useReducedMotion } from 'motion-v'

const repositoryUrl = 'https://github.com/VitorFcosta/ColdSafe'
const reduceMotion = useReducedMotion()
const entrance = computed(() => ({
  initial: { opacity: reduceMotion.value ? 1 : 0, y: reduceMotion.value ? 0 : 16 },
  whileInView: { opacity: 1, y: 0 },
  animate: reduceMotion.value ? { opacity: 1, y: 0 } : undefined,
  inViewOptions: { once: true, amount: 0.1 },
  transition: { duration: reduceMotion.value ? 0 : 0.56 },
}))
const architecture = [
  { number: '01 / CAPTURA', title: 'O ambiente vira dado.', description: 'DHT22 + ESP32 medem temperatura e umidade na simulação.' },
  { number: '02 / TRANSPORTE', title: 'Cada leitura segue seu caminho.', description: 'MQTT transporta a telemetria com reconexão e QoS 1.' },
  { number: '03 / CONTEXTO', title: 'Dados com significado.', description: 'FastAPI valida e classifica. InfluxDB mantém o histórico.' },
  { number: '04 / VISUALIZAÇÃO', title: 'Uma visão do ambiente.', description: 'Vue apresenta o estado atual, a idade da leitura e o gráfico.' },
]
</script>

<template>
  <div class="presentation-theme presentation">
    <a class="skip-link" href="#conteudo">Ir para o conteúdo</a>
    <div class="presentation-shell">
      <header class="navigation">
        <a class="brand" href="/" aria-label="ColdSafe — início"><span aria-hidden="true">◉</span> ColdSafe</a>
        <nav aria-label="Navegação principal">
          <a href="#como-funciona">Como funciona</a>
          <a href="#demonstracao">Demonstração</a>
          <a :href="repositoryUrl">GitHub <span aria-hidden="true">↗</span></a>
        </nav>
      </header>

      <main id="conteudo" class="sections">
        <section class="hero" aria-labelledby="presentation-title">
          <div class="hero-copy">
            <p class="eyebrow">Projeto acadêmico / Internet das coisas</p>
            <h1 id="presentation-title">Cada grau<br />conta.</h1>
            <p class="lead">Da leitura do sensor à decisão. Temperatura, umidade e histórico em uma visão clara do ambiente refrigerado.</p>
            <div class="hero-actions">
              <a class="button button-primary" href="#demonstracao">Ver demonstração</a>
              <a class="button" :href="repositoryUrl">Ver código</a>
            </div>
            <p class="small muted">ESP32 + DHT22 · Vue + FastAPI · MQTT</p>
          </div>
          <figure class="media-frame hero-preview">
            <figcaption class="eyebrow">01 / Visão operacional · Demonstração simulada</figcaption>
            <img
              src="/media/dashboard-normal.png"
              alt="Dashboard ColdSafe com estado normal, temperatura de 5 °C, idade da leitura e histórico de temperatura. Dados simulados."
              width="1440" height="1348" fetchpriority="high"
            />
          </figure>
        </section>

        <dl class="project-facts" aria-label="Características do projeto">
          <div><dt>entre atualizações</dt><dd>05 s</dd></div>
          <div><dt>períodos de histórico</dt><dd>04</dd></div>
          <div><dt>ambiente monitorado</dt><dd>01</dd></div>
        </dl>

        <motion.section v-bind="entrance" class="context reveal" aria-labelledby="context-title">
          <div class="section-heading">
            <p class="eyebrow">01 / Contexto</p>
            <h2 id="context-title">Um número sozinho não conta tudo.</h2>
          </div>
          <div class="context-copy">
            <p class="context-statement">5 °C pode ser uma boa notícia. Se a leitura for de agora.</p>
            <p class="muted">O ColdSafe reúne a medição, a idade da leitura e sua variação ao longo do tempo. Assim, um valor antigo não se confunde com uma situação normal.</p>
            <p class="eyebrow">Valor + atualidade + histórico</p>
          </div>
        </motion.section>

        <section id="como-funciona" class="content-section" aria-labelledby="architecture-title">
          <motion.div v-bind="entrance" class="section-heading reveal">
            <p class="eyebrow">02 / Como funciona</p>
            <h2 id="architecture-title">Do sensor à sua tela.</h2>
            <p class="lead">Uma cadeia completa de hardware, comunicação e software. Cada etapa tem uma responsabilidade.</p>
          </motion.div>
          <ol class="architecture-grid">
            <motion.li
              v-for="(step, index) in architecture" :key="step.number"
              v-bind="entrance"
              :transition="{ duration: reduceMotion ? 0 : 0.56, delay: reduceMotion ? 0 : index * 0.08 }"
              class="architecture-step reveal"
            >
              <p class="eyebrow">{{ step.number }}</p>
              <h3>{{ step.title }}</h3>
              <p class="muted">{{ step.description }}</p>
            </motion.li>
          </ol>
        </section>

        <section id="demonstracao" class="content-section" aria-labelledby="demo-title">
          <motion.div v-bind="entrance" class="section-heading reveal">
            <p class="eyebrow">03 / Demonstração</p>
            <h2 id="demo-title">Veja os dados<br />ganharem contexto.</h2>
            <p class="lead">Do estado normal à leitura desatualizada. Explore o comportamento do painel nesta demonstração gravada com dados simulados.</p>
          </motion.div>
          <figure class="media-frame demo-video">
            <video
              controls preload="metadata" playsinline
              src="/media/coldsafe-demo.webm" poster="/media/dashboard-normal.png"
              aria-label="Demonstração do dashboard ColdSafe com dados simulados"
              aria-describedby="video-description"
            >
              <track kind="captions" src="/media/coldsafe-demo.vtt" srclang="pt-BR" label="Português" default />
              Seu navegador não reproduz este vídeo. <a href="/media/coldsafe-demo.webm">Baixar demonstração</a>.
            </video>
            <figcaption id="video-description">
              <span class="eyebrow">Demonstração simulada</span>
              <p>O vídeo percorre as leituras, a troca de período e os estados do painel. Uma temperatura fora da faixa gera um estado crítico; uma leitura antiga informa que a situação atual não está confirmada.</p>
            </figcaption>
          </figure>
          <div class="state-gallery">
            <figure>
              <img src="/media/dashboard-critical.png" alt="Exemplo simulado do dashboard em estado crítico, com a temperatura fora da faixa demonstrativa." width="1440" height="1348" loading="lazy" />
              <figcaption>
                <p class="eyebrow">Cenário simulado / Crítico</p>
                <h3>Quando a temperatura sai da faixa.</h3>
                <p class="muted">O estado crítico ganha destaque sem esconder a medição.</p>
              </figcaption>
            </figure>
            <figure>
              <img src="/media/dashboard-stale.png" alt="Exemplo simulado de leitura desatualizada: o dashboard mostra a última medição conhecida sem confirmar a situação atual." width="1440" height="1348" loading="lazy" />
              <figcaption>
                <p class="eyebrow">Cenário simulado / Leitura desatualizada</p>
                <h3>Quando a leitura deixa de ser atual.</h3>
                <p class="muted">O painel mostra a última leitura conhecida, sem confirmar a situação atual.</p>
              </figcaption>
            </figure>
          </div>
        </section>

        <motion.section v-bind="entrance" class="construction content-section reveal" aria-labelledby="construction-title">
          <div class="section-heading">
            <p class="eyebrow">04 / Construído de ponta a ponta</p>
            <h2 id="construction-title">Hardware encontra software.</h2>
          </div>
          <p class="muted">ESP32 · DHT22 · MQTT · FastAPI · InfluxDB · Vue · TypeScript</p>
          <p class="lead">Um ambiente, um dispositivo e uma cadeia completa de monitoramento. Um projeto acadêmico para explorar a conexão entre o mundo físico e os dados.</p>
          <a class="button" :href="repositoryUrl">Explorar o repositório <span aria-hidden="true">↗</span></a>
        </motion.section>
      </main>

      <footer class="footer">
        <a class="brand" href="/" aria-label="ColdSafe — início"><span aria-hidden="true">◉</span> ColdSafe</a>
        <p>Protótipo acadêmico. Não é equipamento médico, sanitário ou regulatório certificado.</p>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.presentation { min-height: 100vh; padding: var(--cs-space-48); background: var(--cs-color-canvas); color: var(--cs-color-ink); line-height: 1.5; }
.presentation-shell { max-width: 1200px; margin-inline: auto; }
.navigation, .navigation nav, .brand, .hero-actions, .footer { display: flex; align-items: center; }
.navigation { justify-content: space-between; gap: var(--cs-space-32); padding-bottom: var(--cs-space-48); border-bottom: 1px solid var(--cs-color-line); }
.navigation nav { flex-wrap: wrap; gap: var(--cs-space-32); font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.navigation nav a { min-height: 44px; display: inline-flex; align-items: center; gap: var(--cs-space-4); }
a { text-decoration: none; transition: color var(--cs-motion-quick), background-color var(--cs-motion-quick); }
a:hover { color: var(--cs-color-accent); }
.brand { gap: var(--cs-space-12); font-size: var(--cs-type-24); font-weight: 650; white-space: nowrap; }
.skip-link { position: fixed; top: var(--cs-space-16); left: var(--cs-space-16); z-index: 10; padding: var(--cs-space-12); transform: translateY(-200%); background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
.skip-link:focus { transform: none; }
.sections { display: flex; flex-direction: column; gap: var(--cs-space-64); padding-block: var(--cs-space-64); }
.hero { display: grid; grid-template-columns: minmax(0, 528fr) minmax(0, 624fr); align-items: center; gap: var(--cs-space-48); }
.hero-copy, .context-copy, .section-heading { display: flex; flex-direction: column; align-items: start; gap: var(--cs-space-24); }
h1, h2, h3 { text-wrap: balance; }
h1 { font-size: var(--cs-type-80); font-weight: 500; line-height: 1.1; letter-spacing: -0.045em; }
h2 { font-size: var(--cs-type-48); font-weight: 600; line-height: 1.1; letter-spacing: -0.035em; }
h3 { font-size: var(--cs-type-24); font-weight: 600; line-height: 1.4; letter-spacing: -0.02em; }
.eyebrow { font-size: var(--cs-type-12); font-weight: 500; color: var(--cs-color-accent); text-transform: uppercase; letter-spacing: 0.035em; }
.muted, .lead { color: var(--cs-color-ink-muted); }
.lead { font-size: var(--cs-type-20); max-width: 62ch; }
.small { font-size: var(--cs-type-12); }
.hero-actions { flex-wrap: wrap; gap: var(--cs-space-16); }
.button { display: inline-flex; align-items: center; justify-content: center; gap: var(--cs-space-8); min-height: 48px; padding: var(--cs-space-12) var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); font-size: var(--cs-type-14); font-weight: 500; }
.button:hover { background: var(--cs-color-surface-muted); }
.button-primary { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
.button-primary:hover { background: var(--cs-color-accent-hover); color: var(--cs-color-accent-ink); }
.hero-actions .button-primary { min-width: 224px; }
.hero-actions .button:not(.button-primary) { min-width: 160px; }
.media-frame { display: flex; flex-direction: column; gap: var(--cs-space-16); padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); min-width: 0; }
.hero-preview img { display: block; width: 100%; aspect-ratio: 1.12; object-fit: cover; object-position: top; }
.project-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-48); padding-block: var(--cs-space-32); border-block: 1px solid var(--cs-color-line); }
.project-facts div { display: flex; flex-direction: column-reverse; gap: var(--cs-space-8); }
.project-facts dt { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.project-facts dd { font-size: var(--cs-type-32); font-weight: 500; line-height: 1.1; }
.context { display: grid; grid-template-columns: minmax(0, 528fr) minmax(0, 608fr); gap: var(--cs-space-64); }
.context-statement { font-size: var(--cs-type-24); font-weight: 500; }
.content-section { display: flex; flex-direction: column; align-items: start; gap: var(--cs-space-32); scroll-margin-top: var(--cs-space-24); }
.architecture-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--cs-space-16); list-style: none; width: 100%; }
.architecture-step { display: flex; flex-direction: column; gap: var(--cs-space-24); padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); }
.architecture-step .muted { font-size: var(--cs-type-14); }
.demo-video { width: 100%; }
.demo-video video { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: var(--cs-color-canvas); }
.demo-video figcaption { display: grid; gap: var(--cs-space-8); color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); }
.state-gallery { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-24); width: 100%; }
.state-gallery img { display: block; width: 100%; aspect-ratio: 1.45; object-fit: cover; object-position: top; border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-8); }
.state-gallery figcaption { display: flex; flex-direction: column; gap: var(--cs-space-12); padding-top: var(--cs-space-24); }
.state-gallery h3 { font-size: var(--cs-type-20); }
.state-gallery .muted { font-size: var(--cs-type-14); }
.construction { padding-top: var(--cs-space-48); border-top: 1px solid var(--cs-color-line); }
.footer { justify-content: space-between; gap: var(--cs-space-48); padding-top: var(--cs-space-32); border-top: 1px solid var(--cs-color-line); }
.footer p { max-width: 48ch; color: var(--cs-color-ink-muted); font-size: var(--cs-type-12); text-align: right; }
@media (max-width: 1100px) {
  .hero { gap: var(--cs-space-32); }
  h1 { font-size: var(--cs-type-64); }
  .architecture-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .presentation { padding: var(--cs-space-24); }
  .navigation { align-items: start; flex-direction: column; gap: var(--cs-space-16); padding-bottom: var(--cs-space-24); }
  .navigation nav { gap: var(--cs-space-24); font-size: var(--cs-type-12); }
  .sections { gap: var(--cs-space-48); padding-block: var(--cs-space-48); }
  .hero, .context, .state-gallery { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-32); }
  h1 { font-size: var(--cs-type-48); }
  h2 { font-size: var(--cs-type-32); }
  .lead, .context-statement { font-size: var(--cs-type-20); }
  .hero-actions { gap: var(--cs-space-12); }
  .hero-actions .button, .hero-actions .button-primary, .hero-actions .button:not(.button-primary) { min-width: 0; padding-inline: var(--cs-space-16); }
  .project-facts { gap: var(--cs-space-16); }
  .project-facts dd { font-size: var(--cs-type-24); }
  .project-facts dt { font-size: var(--cs-type-12); }
  .architecture-grid { grid-template-columns: minmax(0, 1fr); }
  .architecture-step { gap: var(--cs-space-16); }
  .footer { align-items: start; flex-direction: column; gap: var(--cs-space-24); }
  .footer p { text-align: left; }
}
@media (max-width: 374px) {
  .presentation { padding: var(--cs-space-16); }
  .hero-actions { align-items: stretch; flex-direction: column; width: 100%; }
  .navigation nav { gap: var(--cs-space-16); }
}
@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1 !important; transform: none !important; }
}
</style>
