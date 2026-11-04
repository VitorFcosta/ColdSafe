<script setup lang="ts">
import { ref } from 'vue'

const repositoryUrl = 'https://github.com/VitorFcosta/ColdSafe'
const video = ref<HTMLVideoElement | null>(null)
const videoFailed = ref(false)
const captionsFailed = ref(false)
const mobileMenu = ref<HTMLDetailsElement | null>(null)
const architecture = [
  { title: 'Sensores e transmissão', description: 'O simulador Python gera seis grandezas do ambiente e do motor. A telemetria segue por MQTT até o gateway.' },
  { title: 'Processamento e histórico', description: 'O gateway valida os eventos e os encaminha pelo RabbitMQ. InfluxDB guarda as leituras; PostgreSQL mantém contas, regras e a projeção consultada pela API.' },
  { title: 'Interface e inspeção', description: 'Vue reúne histórico, alertas e inspeção 3D. Saúde e vida útil restante são estimativas de modelos treinados com dados sintéticos.' },
]

function retryVideo() {
  videoFailed.value = false
  video.value?.focus()
  video.value?.load()
}
</script>

<template>
  <div class="presentation-theme presentation">
    <a class="skip-link" href="#conteudo">Ir para o conteúdo</a>
    <div class="presentation-shell">
      <header class="navigation">
        <a class="brand" href="/" aria-label="ColdSafe — início">ColdSafe</a>
        <nav class="desktop-nav" aria-label="Navegação principal">
          <a href="#como-funciona">Como funciona</a>
          <a href="#demonstracao">Demonstração</a>
          <a :href="repositoryUrl">GitHub</a>
        </nav>
        <RouterLink class="button access-link" to="/dashboard">Acessar painel</RouterLink>
        <details ref="mobileMenu" class="mobile-nav">
          <summary>Menu</summary>
          <nav aria-label="Navegação principal móvel" @click="mobileMenu && (mobileMenu.open = false)">
            <a href="#como-funciona">Como funciona</a>
            <a href="#demonstracao">Demonstração</a>
            <a :href="repositoryUrl">GitHub</a>
          </nav>
        </details>
      </header>

      <main id="conteudo" tabindex="-1" class="sections">
        <section class="hero" aria-labelledby="presentation-title">
          <div class="hero-copy">

            <h1 id="presentation-title" tabindex="-1">Da leitura do sensor à compreensão do equipamento.</h1>
            <p class="lead">Sensores, histórico e inspeção reunidos num projeto demonstrativo.</p>
            <p class="small muted">Protótipo acadêmico · AIoT</p>
            <div class="hero-actions">
              <a class="button button-primary" href="#demonstracao">Ver demonstração</a>
              <a class="button" :href="repositoryUrl">Ver código</a>
            </div>
          </div>
          <figure class="hero-preview">
            <img src="/media/equipamento-conceitual-p05.png" alt="Ilustração conceitual de um ventilador instrumentado sobre uma base com sensores. Não é fotografia do protótipo." width="1536" height="1024" fetchpriority="high" />
            <figcaption>Representação ilustrativa · imagem gerada por IA. Não define o hardware ou a posição real dos sensores.</figcaption>
          </figure>
        </section>

        <section id="como-funciona" tabindex="-1" class="content-section" aria-labelledby="architecture-title">
          <div class="section-heading">
            <h2 id="architecture-title">Como os dados chegam até aqui</h2>
            <p class="muted">Aquisição → transmissão → processamento → visualização</p>
          </div>
          <ol class="architecture-grid">
            <li v-for="step in architecture" :key="step.title" class="architecture-step">
              <h3>{{ step.title }}</h3>
              <p class="muted">{{ step.description }}</p>
            </li>
          </ol>
          <p class="small muted">ESP32 com DHT22 no Wokwi permanece como caminho legado opcional. A demonstração AIoT atual usa sensores simulados, sem validar desempenho físico.</p>
        </section>

        <section class="context content-section" aria-labelledby="context-title">
          <div class="section-heading">
            <h2 id="context-title">Um número sozinho não conta tudo.</h2>
          </div>
          <div class="context-copy">
            <p class="context-statement">5 °C pode ser uma boa notícia. Se a leitura for de agora.</p>
            <p class="muted">O ColdSafe reúne a medição, a idade da leitura e sua variação ao longo do tempo. Assim, um valor antigo não se confunde com uma situação normal.</p>
            <p class="muted">A inspeção 3D permite selecionar componentes e consultar seus dados. O movimento é ilustrativo: não mede RPM nem representa uma simulação física validada.</p>
          </div>
        </section>

        <section id="demonstracao" tabindex="-1" class="content-section" aria-labelledby="demo-title">
          <div class="section-heading">
            <h2 id="demo-title">Veja os dados ganharem contexto.</h2>
            <p class="lead">Do estado normal à leitura desatualizada. Uma demonstração gravada da interface, com respostas HTTP simuladas.</p>
          </div>
          <figure class="media-frame demo-video">
            <video
              ref="video" controls preload="metadata" playsinline tabindex="0"
              src="/media/coldsafe-demo.webm" poster="/media/dashboard-normal.png"
              aria-label="Demonstração do dashboard ColdSafe com dados simulados"
              aria-describedby="video-description"
              @error="videoFailed = true" @loadedmetadata="videoFailed = false"
            >
              <track kind="captions" src="/media/coldsafe-demo.vtt" srclang="pt-BR" label="Português" default @error="captionsFailed = true" @load="captionsFailed = false" />
              Seu navegador não reproduz este vídeo. A demonstração também está disponível para download e em texto abaixo.
            </video>
            <figcaption id="video-description">
              <strong>Demonstração simulada · versão anterior da interface</strong>
              <p>Gravação documentada em setembro de 2026. Não demonstra a pilha AIoT atual nem atuação física. Sem narração; legendas descritivas em português.</p>
              <p>O vídeo percorre leituras, histórico e estados do painel. Uma leitura antiga não confirma a situação atual. O LED só aparece ligado após a confirmação simulada do comando.</p>
            </figcaption>
            <div v-if="videoFailed" class="media-error">
              <div role="status">
                <h3>Vídeo indisponível</h3>
                <p>A demonstração não pôde ser carregada. O restante da apresentação continua disponível. Tente novamente ou leia a transcrição abaixo.</p>
              </div>
              <button class="button" type="button" data-testid="retry-video" @click="retryVideo">Tentar carregar vídeo</button>
            </div>
            <p v-if="captionsFailed" class="caption-error">As legendas não puderam ser carregadas. <a href="#transcript">Ler transcrição da demonstração</a>.</p>
            <div class="media-links">
              <a href="/media/coldsafe-demo.webm" download>Baixar demonstração (WebM, 6,1 MB)</a>
              <a href="/media/coldsafe-demo.vtt" download>Baixar legendas em português</a>
            </div>
            <section id="transcript" tabindex="-1" class="transcript" aria-labelledby="transcript-title">
              <h3 id="transcript-title">Demonstração em texto</h3>
              <ol>
                <li>0–9 s: temperatura, estado e idade da leitura simulada aparecem juntos.</li>
                <li>10–19 s: o período de 24 horas mostra a variação da temperatura simulada.</li>
                <li>19–28 s: o estado de atenção indica proximidade do limite demonstrativo.</li>
                <li>28–37 s: temperatura simulada fora da faixa recebe estado crítico, com texto e cor.</li>
                <li>37–48 s: uma leitura antiga dentro da faixa não confirma a condição atual.</li>
                <li>48–59 s: falha simulada no histórico preserva o diagnóstico atual.</li>
                <li>59–69 s: uma nova consulta recupera o histórico simulado.</li>
                <li>69–81 s: o comando LED passa por pendente e só aparece ligado após confirmação simulada.</li>
              </ol>
            </section>
          </figure>
          <div class="state-gallery">
            <figure>
              <img src="/media/dashboard-critical.png" alt="Versão anterior da interface com temperatura simulada fora da faixa demonstrativa e estado crítico." width="1440" height="1080" loading="lazy" />
              <figcaption>
                <h3>Quando a temperatura sai da faixa.</h3>
                <p class="muted">O estado crítico ganha destaque sem esconder a medição. Captura anterior com dados simulados.</p>
              </figcaption>
            </figure>
            <figure>
              <img src="/media/dashboard-stale.png" alt="Versão anterior da interface com leitura simulada desatualizada, apresentada como última medição conhecida." width="1440" height="1080" loading="lazy" />
              <figcaption>
                <h3>Quando a leitura deixa de ser atual.</h3>
                <p class="muted">O painel mostra a última leitura conhecida, sem confirmar a situação atual. Captura anterior com dados simulados.</p>
              </figcaption>
            </figure>
          </div>
        </section>

        <section class="construction content-section" aria-labelledby="construction-title">
          <div class="section-heading"><h2 id="construction-title">Hardware encontra software.</h2></div>
          <p class="muted">Python · MQTT · FastAPI · InfluxDB · PostgreSQL · RabbitMQ · Vue · TypeScript · Three.js</p>
          <p class="lead">Este projeto acadêmico explora a conexão entre o mundo físico e os dados. Ambientes e dispositivos ficam vinculados à conta; as ações disponíveis dependem das permissões.</p>
          <p class="muted">Saúde e vida útil restante usam dados sintéticos: não comprovam a confiabilidade de um equipamento real. O assistente local pode errar e não comanda dispositivos. Consulte o repositório para conhecer os contratos, os ensaios e os limites do protótipo.</p>
          <a class="button" :href="repositoryUrl">Explorar o repositório</a>
        </section>
      </main>

      <footer class="footer">
        <a class="brand" href="/" aria-label="ColdSafe — início">ColdSafe</a>
        <p>Protótipo acadêmico. Não é equipamento médico, sanitário ou regulatório certificado.</p>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.presentation { min-height: 100vh; padding: var(--cs-space-32) var(--cs-space-64) var(--cs-space-48); background: var(--cs-color-canvas); color: var(--cs-color-ink); line-height: 1.5; overflow-wrap: anywhere; }
.presentation ::selection { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); }
.presentation-shell { max-width: 1280px; margin-inline: auto; }
p, h1, h2, h3, figure, ol { margin: 0; }
.navigation, .navigation nav, .brand, .hero-actions, .footer { display: flex; align-items: center; }
.navigation { gap: var(--cs-space-32); }
.navigation .brand { margin-right: auto; }
.navigation nav { flex-wrap: wrap; gap: var(--cs-space-32); font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.navigation nav a { min-height: var(--cs-control-min-height); display: inline-flex; align-items: center; }
.mobile-nav { display: none; }
a { text-decoration: underline; text-underline-offset: .2em; transition: color var(--cs-motion-quick), background-color var(--cs-motion-quick); }
a:hover { color: var(--cs-color-accent); }
.brand { min-height: var(--cs-control-min-height); font-size: var(--cs-type-24); font-weight: 650; text-decoration: none; }
.sections { display: flex; flex-direction: column; gap: var(--cs-space-64); padding-block: var(--cs-space-64); }
.hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr); align-items: center; gap: var(--cs-space-48); }
.hero-copy, .context-copy, .section-heading { display: flex; flex-direction: column; align-items: start; gap: var(--cs-space-24); }
.hero-copy { animation: enter var(--cs-motion-entrance) cubic-bezier(.16, 1, .3, 1); }
@keyframes enter { from { transform: translateY(12px); } to { transform: translateY(0); } }
h1, h2, h3 { text-wrap: balance; }
h1 { font-size: var(--cs-type-48); font-weight: 650; line-height: 1.1667; letter-spacing: -.025em; }
h2 { font-size: var(--cs-type-32); font-weight: 650; line-height: 1.25; }
h3 { font-size: var(--cs-type-20); font-weight: 650; line-height: 1.4; }
.muted, .lead { color: var(--cs-color-ink-muted); }
.lead { font-size: var(--cs-type-20); max-width: 62ch; }
.small, figcaption { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
.hero-actions { flex-wrap: wrap; gap: var(--cs-space-16); margin-top: var(--cs-space-24); }
.button { display: inline-flex; align-items: center; justify-content: center; min-height: var(--cs-control-min-height); padding: var(--cs-space-12) var(--cs-space-24); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); font-family: inherit; font-size: var(--cs-type-14); font-weight: 600; line-height: 1.4286; text-decoration: none; cursor: pointer; text-align: center; }
.button:hover { background: var(--cs-color-surface-muted); color: var(--cs-color-ink); }
.button-primary, .access-link { background: var(--cs-color-accent); color: var(--cs-color-accent-ink); border-color: transparent; }
.button-primary:hover, .access-link:hover { background: var(--cs-color-accent-hover); color: var(--cs-color-accent-ink); }
.hero-preview { min-width: 0; padding: var(--cs-space-12); border-radius: var(--cs-radius-8); background: #f3f6f5; color: #526c70; }
.hero-preview img { display: block; width: 100%; height: auto; }
.hero-preview figcaption { margin-top: var(--cs-space-8); color: inherit; }
.content-section { display: flex; flex-direction: column; align-items: start; gap: var(--cs-space-32); scroll-margin-top: var(--cs-space-24); }
.architecture-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--cs-space-24); padding: 0; list-style: none; width: 100%; }
.architecture-step { display: flex; flex-direction: column; gap: var(--cs-space-16); padding: var(--cs-space-24); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); }
.architecture-step h3 { color: var(--cs-color-accent); }
.architecture-step p { font-size: var(--cs-type-14); }
.context { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cs-space-48); border-block: 1px solid var(--cs-color-line); padding-block: var(--cs-space-48); }
.context-statement { font-size: var(--cs-type-24); }
.media-frame { display: grid; gap: var(--cs-space-24); padding: var(--cs-space-24); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-16); background: var(--cs-color-surface); min-width: 0; width: 100%; }
.demo-video video { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: var(--cs-color-canvas); }
.demo-video figcaption { display: grid; gap: var(--cs-space-12); }
.media-error { display: grid; justify-items: start; gap: var(--cs-space-16); padding: var(--cs-space-24); background: var(--cs-color-stale-surface); border-radius: var(--cs-radius-8); }
.media-error p { margin-top: var(--cs-space-12); }
.media-links { display: flex; flex-wrap: wrap; gap: var(--cs-space-16) var(--cs-space-32); }
.media-links a { display: inline-flex; align-items: center; min-height: var(--cs-control-min-height); }
.transcript { border-top: 1px solid var(--cs-color-line); padding-top: var(--cs-space-24); }
.transcript ol { margin-top: var(--cs-space-16); padding-left: var(--cs-space-24); color: var(--cs-color-ink-muted); }
.transcript li + li { margin-top: var(--cs-space-8); }
.state-gallery { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--cs-space-32); width: 100%; }
.state-gallery img { display: block; width: 100%; height: auto; border-radius: var(--cs-radius-8); }
.state-gallery figcaption { display: grid; gap: var(--cs-space-12); padding-top: var(--cs-space-24); }
.state-gallery h3 { color: var(--cs-color-ink); }
.construction { padding-top: var(--cs-space-48); border-top: 1px solid var(--cs-color-line); }
.construction p { max-width: 70ch; }
.footer { justify-content: space-between; gap: var(--cs-space-48); padding-top: var(--cs-space-32); border-top: 1px solid var(--cs-color-line); }
.footer p { max-width: 48ch; color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); text-align: right; }
@media (max-width: 1000px) {
  .presentation { padding-inline: var(--cs-space-32); }
  .navigation { gap: var(--cs-space-16); }
  .navigation nav { gap: var(--cs-space-16); }
  .hero { gap: var(--cs-space-32); }
  .architecture-grid { grid-template-columns: 1fr; }
}
@media (max-width: 767px) {
  .presentation { padding: var(--cs-space-24); }
  .navigation { position: relative; flex-wrap: wrap; gap: var(--cs-space-12); }
  .desktop-nav { display: none !important; }
  .mobile-nav { display: block; margin-left: auto; }
  .mobile-nav summary { min-height: var(--cs-control-min-height); padding: var(--cs-space-8) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); cursor: pointer; }
  .mobile-nav nav { position: absolute; z-index: 2; top: calc(100% + var(--cs-space-8)); right: 0; max-width: 100%; display: flex; flex-direction: column; align-items: stretch; gap: 0; padding: var(--cs-space-8); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); }
  .mobile-nav nav a { padding-inline: var(--cs-space-12); }
  .sections { gap: var(--cs-space-48); padding-block: var(--cs-space-48); }
  .hero, .context, .state-gallery { grid-template-columns: minmax(0, 1fr); gap: var(--cs-space-32); }
  h1, h2 { font-size: var(--cs-type-32); }
  .lead { font-size: var(--cs-type-16); }
  .hero-actions { margin-top: var(--cs-space-8); gap: var(--cs-space-12); }
  .hero-actions .button { padding-inline: var(--cs-space-16); }
  .media-frame { padding: var(--cs-space-16); }
  .media-error { padding: var(--cs-space-16); }
  .footer { align-items: start; flex-direction: column; gap: var(--cs-space-24); }
  .footer p { text-align: left; }
}
@media (max-width: 374px) {
  .presentation { padding-inline: var(--cs-space-16); }
  .hero-actions { align-items: stretch; flex-direction: column; width: 100%; }
}
@media (prefers-reduced-motion: reduce) { .hero-copy { animation: none; } }
</style>
