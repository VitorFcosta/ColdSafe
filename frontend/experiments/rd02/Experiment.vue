<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import OriginalScene from './LegacyScene.vue'
import { buildTwinItems, buildTwinVisualState, twinStatusLabels } from '../../src/features/digital-twin/twin-state'
import CandidateScene from '../../src/features/digital-twin/DigitalTwinScene.vue'
import { controlledSummary, type ExperimentState } from './fixtures'
import { installProbe } from './probe'

const probe = installProbe()
const mode = ref<'baseline' | 'candidate'>('candidate')
const state = ref<ExperimentState>('active')
const mounted = ref(true)
const candidate = ref<InstanceType<typeof CandidateScene> | null>(null)
const selectedId = ref<string | null>(null)
const summary = computed(() => controlledSummary(state.value))
const fresh = computed(() => state.value !== 'stale' && state.value !== 'empty')
const items = computed(() => buildTwinItems(summary.value, fresh.value, null))
const visual = computed(() => buildTwinVisualState(summary.value, fresh.value))
const selected = computed(() => items.value.find((item) => item.id === selectedId.value))
watch(mode, () => { selectedId.value = null })

// API restrita à página de ensaio; nenhum renderer/controle é exposto no aplicativo.
Object.assign(window, { rd02: {
  probe,
  snapshot: () => candidate.value?.snapshot() ?? null,
  items: () => items.value,
  projection: () => candidate.value?.projected() ?? [],
  async setScene(value: 'baseline' | 'candidate') { mode.value = value; await nextTick() },
  async setVisual(value: ExperimentState) { state.value = value; await nextTick() },
  async mount(value: boolean) { mounted.value = value; await nextTick() },
  async select(id: string) { selectedId.value = items.value.some((item) => item.id === id) ? id : null; await nextTick() },
} })
onUnmounted(() => { probe.uninstall(); Reflect.deleteProperty(window, 'rd02') })
</script>

<template>
  <main class="experiment cs-controls">
    <a class="skip-link" href="#components">Ir para os componentes</a>
    <header>
      <h1>Experimento do gêmeo 3D</h1>
      <p>RD-02 · Geometria própria em Three.js · <strong>Dados simulados</strong></p>
      <p class="explanation">Compare a cena frontal arquivada com a cena em três quartos integrada na RD-09. Este ensaio não consulta a API nem atua em dispositivos. O snapshot é fixo: atualidade e estados são impostos pelos controles abaixo para testar a renderização.</p>
    </header>
    <div class="controls">
      <label>Cena<select v-model="mode" name="scene"><option value="candidate">Produção — três quartos</option><option value="baseline">Arquivada — frontal</option></select></label>
      <label>Cenário controlado<select v-model="state" name="state"><option value="active">Leitura atual · em operação</option><option value="changed">Nova leitura · LED e buzzer ligados</option><option value="stale">Leitura vencida</option><option value="stopped">Equipamento parado</option><option value="zero">Valores zero</option><option value="empty">Sem leitura</option></select></label>
      <button type="button" :aria-pressed="mounted" @click="mounted = !mounted">{{ mounted ? 'Desmontar cena' : 'Montar cena' }}</button>
    </div>
    <div class="workspace">
      <section class="stage" aria-labelledby="scene-title">
        <h2 id="scene-title">{{ mode === 'candidate' ? 'Produção — geometria refinada' : 'Cena frontal arquivada — referência funcional' }}</h2>
        <template v-if="mounted">
          <CandidateScene v-if="mode === 'candidate'" ref="candidate" :items="items" :visual="visual" :selected-id="selectedId" @select="selectedId = $event" />
          <OriginalScene v-else :items="items" :visual="visual" :selected-id="selectedId" @select="selectedId = $event" />
        </template>
        <p v-else role="status">Cena desmontada. Lista e dados continuam disponíveis.</p>
        <p v-if="selected" class="selection-summary"><strong>{{ selected.label }}</strong>: {{ selected.value }} · {{ twinStatusLabels[selected.status] }}</p>
        <a class="components-link" href="#components">Ver componentes</a>
      </section>
      <aside>
        <section id="components" aria-labelledby="components-title">
          <h2 id="components-title">Componentes</h2>
          <p>Mesmo inventário nas duas cenas. Sensores sem regra não recebem diagnóstico físico; “Normal” é o estado atual da base existente.</p>
          <ul>
            <li v-for="item in items" :key="item.key"><button type="button" :disabled="!item.id" :aria-pressed="item.id !== null && selectedId === item.id" @click="selectedId = item.id"><strong>{{ item.label }}</strong><span>{{ item.value }} · {{ twinStatusLabels[item.status] }}</span></button></li>
          </ul>
        </section>
        <section class="inspector" aria-labelledby="inspector-title" :data-selected-id="selectedId ?? ''">
          <h2 id="inspector-title">{{ selected?.label ?? 'Inspecione um componente' }}</h2>
          <template v-if="selected"><p>{{ selected.value }} · {{ twinStatusLabels[selected.status] }}</p><p class="identifier">ID: {{ selected.id }}</p><p>Horário da fixture: {{ summary.reading?.received_at ?? 'Sem leitura' }}</p><p>Saúde/RUL: {{ selected.kind === 'equipment' ? 'Sem previsão neste ensaio.' : 'Não aplicável a este item.' }}</p></template>
          <p v-else>Selecione na cena ou na lista. Nenhuma seleção envia comandos.</p>
        </section>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.experiment { max-width: 1600px; margin: auto; padding: var(--cs-space-32); }
h1 { font-size: var(--cs-type-32); margin: 0; } h2 { font-size: var(--cs-type-20); margin: 0 0 var(--cs-space-16); }
header { margin-bottom: var(--cs-space-24); }
.explanation { max-width: 75ch; color: var(--cs-color-ink-muted); }
.controls { display: flex; flex-wrap: wrap; align-items: end; gap: var(--cs-space-16); margin-bottom: var(--cs-space-32); }
.controls select { width: 100%; min-width: 0; max-width: 100%; min-height: var(--cs-control-min-height); padding: var(--cs-space-8) var(--cs-space-12); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); font: inherit; font-size: var(--cs-type-16); }
.controls label { display: grid; gap: var(--cs-space-8); min-width: 0; }
.workspace { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: var(--cs-space-32); align-items: start; }
.selection-summary, .components-link { display: none; }
.components-link { color: var(--cs-color-accent); text-decoration: underline; }
.stage, aside { min-width: 0; }
aside p { font-size: var(--cs-type-14); color: var(--cs-color-ink-muted); }
ul { list-style: none; padding: 0; display: grid; gap: var(--cs-space-8); }
li button { width: 100%; text-align: left; display: grid; gap: var(--cs-space-4); }
li span { font-weight: 400; }
li button[aria-pressed='true'] { border-color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
.inspector { margin-top: var(--cs-space-24); padding-top: var(--cs-space-24); border-top: 1px solid var(--cs-color-line); }
.identifier { overflow-wrap: anywhere; }
@media(max-width: 960px) { .selection-summary, .components-link { display: block; } .workspace { grid-template-columns: 1fr; } .experiment { padding: var(--cs-space-16); } h1 { font-size: var(--cs-type-24); } .controls { display: grid; grid-template-columns: minmax(0, 1fr); } }
</style>
