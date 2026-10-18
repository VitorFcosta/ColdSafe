<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from 'vue'
import { Chart as ChartJS, Legend, LineElement, LinearScale, PointElement, Tooltip, type ChartData, type ChartOptions } from 'chart.js'
import { Scatter } from 'vue-chartjs'
import { sensorChoices } from '../laboratory/laboratory-api'
import type { TargetResult } from './training-api'
ChartJS.register(Legend, LineElement, LinearScale, PointElement, Tooltip)
const props = defineProps<{ result: TargetResult }>()
const root = useTemplateRef<HTMLElement>('root')
const colors = ref({ accent: '#086c74', muted: '#59666b', line: '#cad4d6' })
onMounted(() => { const style = getComputedStyle(root.value!); colors.value = { accent: style.getPropertyValue('--cs-color-accent').trim() || colors.value.accent,
  muted: style.getPropertyValue('--cs-color-ink-muted').trim() || colors.value.muted, line: style.getPropertyValue('--cs-color-line').trim() || colors.value.line } })
const name = computed(() => props.result.target === 'health_score_true' ? 'Saúde' : 'Vida útil restante (RUL)')
const unit = computed(() => props.result.unit === 'points' ? 'pontos de saúde' : 'horas')
const number = (v: number | null) => v === null ? 'Indefinido (alvo constante)' : new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 4 }).format(v)
const partitions = [['validation', 'Validação'], ['test', 'Teste reservado']] as const
const features = computed(() => [...props.result.diagnostics.permutation.features].sort((a, b) => b.mean - a.mean))
const maxImportance = computed(() => Math.max(...features.value.map((f) => Math.abs(f.mean)), Number.EPSILON))
function featureLabel(key: string) {
  const sensor = sensorChoices.find(([id]) => key.startsWith(id))
  return sensor ? `${sensor[1]} · ${key.slice(sensor[0].length).replace(/^_/, '') || 'valor'}` : key
}
const chartData = computed<ChartData<'scatter'>>(() => {
  const points = props.result.diagnostics.scatter
  const min = Math.min(...points.flatMap((p) => [p.actual, p.predicted]))
  const max = Math.max(...points.flatMap((p) => [p.actual, p.predicted]))
  return { datasets: [
    { label: 'Candidato', data: points.map((p) => ({ x: p.actual, y: p.predicted })), backgroundColor: colors.value.accent, pointRadius: 3 },
    { label: 'Previsão perfeita', data: [{ x: min, y: min }, { x: max, y: max }], showLine: true, pointRadius: 0, borderDash: [5, 5], borderColor: colors.value.muted, borderWidth: 1 },
  ] }
})
const options = computed<ChartOptions<'scatter'>>(() => ({ responsive: true, maintainAspectRatio: false, animation: false,
  plugins: { legend: { labels: { color: colors.value.muted } } }, scales: {
    x: { type: 'linear', title: { display: true, text: `Real (${unit.value})`, color: colors.value.muted }, grid: { color: colors.value.line }, ticks: { color: colors.value.muted } },
    y: { type: 'linear', title: { display: true, text: `Previsto (${unit.value})`, color: colors.value.muted }, grid: { color: colors.value.line }, ticks: { color: colors.value.muted } },
  } }))
</script>

<template>
  <section ref="root" class="target" :aria-label="`Resultados de ${name}`">
    <h2>{{ name }} <span class="unit">{{ unit }}</span></h2>
    <p class="verdict">{{ result.status === 'eligible' ? 'Apto pela validação' : 'Rejeitado pela validação' }}</p>
    <p>O candidato supera a baseline quando seu MAE de validação é menor. A seleção usa somente a validação. O teste reservado mede a generalização depois da escolha. Apto não significa modelo ativo nem precisão operacional comprovada.</p>
    <p>MAE e RMSE: menor é melhor ({{ unit }}). R²: maior é melhor; pode ser negativo. Baseline prevê um valor constante aprendido no treino.</p>
    <div class="table-scroll" role="region" :aria-label="`Métricas de ${name}`" tabindex="0">
      <table><caption>Comparação no conjunto completo de cada partição</caption><thead><tr><th scope="col">Partição</th><th scope="col">Modelo</th><th scope="col">MAE</th><th scope="col">RMSE</th><th scope="col">R²</th></tr></thead>
        <tbody><template v-for="[key, label] in partitions" :key="key"><tr v-for="model in (['baseline', 'candidate'] as const)" :key="model"><th scope="row">{{ label }}</th><td>{{ model === 'baseline' ? 'Baseline' : 'Candidato' }}</td><td>{{ number(result.metrics[key][model].mae) }}</td><td>{{ number(result.metrics[key][model].rmse) }}</td><td>{{ number(result.metrics[key][model].r2) }}</td></tr></template></tbody>
      </table>
    </div>
    <p>Linhas: treino {{ number(result.partition_rows.train) }}, validação {{ number(result.partition_rows.validation) }}, teste {{ number(result.partition_rows.test) }}.</p>
    <h3>Previsto × real</h3>
    <p>{{ result.diagnostics.sample_count }} de {{ number(result.diagnostics.total_rows) }} linhas do teste, sorteadas sem reposição após a escolha (seed {{ result.diagnostics.sample_seed }}; máximo 500). Pontos próximos da diagonal indicam previsões próximas do valor real. Erro = previsto − real; positivo superestima.</p>
    <div class="chart" role="img" :aria-label="`Previsto versus real de ${name}, em ${unit}; tabela de erros disponível abaixo`"><Scatter :data="chartData" :options="options" /></div>
    <details><summary>Inspecionar erros em tabela ({{ result.diagnostics.sample_count }} linhas)</summary>
      <div class="table-scroll sample" role="region" :aria-label="`Erros de ${name}`" tabindex="0"><table><caption>Amostra reservada; valores em {{ unit }}</caption><thead><tr><th scope="col">Real</th><th scope="col">Previsto</th><th scope="col">Baseline</th><th scope="col">Erro</th></tr></thead><tbody><tr v-for="(point, index) in result.diagnostics.scatter" :key="index"><td>{{ number(point.actual) }}</td><td>{{ number(point.predicted) }}</td><td>{{ number(point.baseline) }}</td><td>{{ number(point.error) }}</td></tr></tbody></table></div>
    </details>
    <h3>Importância por permutação</h3>
    <p>Aumento médio de MAE ao embaralhar uma variável, em {{ unit }}, com 3 repetições na mesma amostra reservada. Importância negativa indica melhora na amostra ao embaralhar; não demonstra causalidade. MAE de referência da amostra: {{ number(result.diagnostics.permutation.reference_mae) }}.</p>
    <div class="table-scroll" role="region" :aria-label="`Importância em ${name}`" tabindex="0"><table><caption>Variáveis e variação média de erro; barras mantêm o sinal</caption><thead><tr><th scope="col">Variável</th><th scope="col">Aumento médio do MAE</th><th scope="col">Desvio padrão</th></tr></thead><tbody><tr v-for="feature in features" :key="feature.name"><th scope="row"><span>{{ featureLabel(feature.name) }}</span><small>{{ feature.name }}</small></th><td><span class="importance" aria-hidden="true"><i :class="{ negative: feature.mean < 0 }" :style="{ width: `${Math.abs(feature.mean) / maxImportance * 50}%`, left: feature.mean < 0 ? `${50 - Math.abs(feature.mean) / maxImportance * 50}%` : '50%' }"></i></span>{{ number(feature.mean) }}</td><td>{{ number(feature.std) }}</td></tr></tbody></table></div>
    <template v-if="result.near_failure">
      <h3>Últimas {{ result.near_failure.threshold_hours }} horas antes da falha</h3>
      <p class="warning">Recorte de avaliação: erros ainda podem ser grandes perto da falha. R² negativo indica desempenho pior que prever a média do próprio recorte; não use esta estimativa como garantia operacional.</p>
      <div class="table-scroll" role="region" aria-label="Métricas perto da falha" tabindex="0"><table><caption>RUL perto da falha, em horas</caption><thead><tr><th scope="col">Partição</th><th scope="col">Linhas</th><th scope="col">Modelo</th><th scope="col">MAE</th><th scope="col">RMSE</th><th scope="col">R²</th></tr></thead><tbody><template v-for="[key, label] in partitions" :key="key"><tr v-for="model in (['baseline', 'candidate'] as const)" :key="model"><th scope="row">{{ label }}</th><td>{{ number(result.near_failure[key].row_count) }}</td><td>{{ model === 'baseline' ? 'Baseline' : 'Candidato' }}</td><td>{{ result.near_failure[key][model] ? number(result.near_failure[key][model]!.mae) : 'Sem linhas' }}</td><td>{{ result.near_failure[key][model] ? number(result.near_failure[key][model]!.rmse) : 'Sem linhas' }}</td><td>{{ result.near_failure[key][model] ? number(result.near_failure[key][model]!.r2) : 'Sem linhas' }}</td></tr></template></tbody></table></div>
    </template>
  </section>
</template>

<style scoped>
.target { border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-lg); padding: var(--cs-space-24); background: var(--cs-color-surface); min-width: 0; }
h2 { font-size: var(--cs-type-24); font-weight: 600; } h3 { margin-top: var(--cs-space-24); font-weight: 600; } p { margin-top: var(--cs-space-12); line-height: 1.7; } .unit, small { display: block; font-size: var(--cs-type-12); color: var(--cs-color-ink-muted); } .verdict { font-weight: 700; color: var(--cs-color-accent); }
.table-scroll { overflow: auto; margin-top: var(--cs-space-16); } table { width: 100%; border-collapse: collapse; text-align: left; font-variant-numeric: tabular-nums; } th, td { border-bottom: 1px solid var(--cs-color-line); padding: var(--cs-space-12); white-space: nowrap; } caption { text-align: left; color: var(--cs-color-ink-muted); padding-bottom: var(--cs-space-8); } .chart { height: 320px; margin-top: var(--cs-space-16); } summary { min-height: 44px; cursor: pointer; display: flex; align-items: center; color: var(--cs-color-accent); } .sample { max-height: 320px; } .warning { border-left: 3px solid var(--cs-color-status-attention); padding-left: var(--cs-space-12); }
.importance { display: inline-block; position: relative; height: 10px; width: 100px; margin-right: 12px; background: linear-gradient(to right, transparent 49.5%, var(--cs-color-ink-muted) 49.5%, var(--cs-color-ink-muted) 50.5%, transparent 50.5%); } .importance i { position: absolute; height: 100%; background: var(--cs-color-accent); } .importance i.negative { background: var(--cs-color-status-attention); }
@media (max-width: 600px) { .target { padding: var(--cs-space-16); } .chart { height: 260px; } }
</style>
