<script setup lang="ts">
import { useId, watch } from 'vue'
import { sessionToken } from '../account/session'

const props = defineProps<{ resetKey?: string }>()
const hidden = defineModel<boolean>({ default: false })
const regionId = useId()
watch([sessionToken, () => props.resetKey], () => { hidden.value = false }, { flush: 'sync' })
</script>

<template>
  <div class="live-data-control">
    <button type="button" :aria-expanded="!hidden" :aria-controls="regionId" @click="hidden = !hidden">
      {{ hidden ? 'Mostrar dados ao vivo' : 'Ocultar dados ao vivo' }}
    </button>
    <p role="status">{{ hidden
      ? 'Dados ao vivo ocultos. A coleta e os pedidos em andamento continuam. Ao mostrar, você verá os dados mais recentes recebidos.'
      : 'Ocultar não interrompe a coleta.' }}</p>
  </div>
  <div :id="regionId" :hidden="hidden" data-live-region class="live-data-region"><slot /></div>
</template>

<style scoped>
.live-data-control { display: flex; flex-wrap: wrap; align-items: center; gap: var(--cs-space-12) var(--cs-space-24); margin-block: var(--cs-space-16) var(--cs-space-24); min-width: 0; }
button { min-height: var(--cs-control-min-height); padding: var(--cs-space-12) var(--cs-space-16); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-4); background: var(--cs-color-surface); color: var(--cs-color-accent); font-size: var(--cs-type-14); font-weight: 600; cursor: pointer; overflow-wrap: anywhere; }
button:hover { background: var(--cs-color-surface-muted); }
button:focus-visible { outline: 3px solid var(--cs-focus-ring); outline-offset: 3px; }
p { flex: 1 1 32ch; margin: 0; max-width: 70ch; color: var(--cs-color-ink-muted); font-size: var(--cs-type-14); line-height: 1.6; overflow-wrap: anywhere; }
.live-data-region { display: contents; }
.live-data-region[hidden] { display: none; }
</style>
