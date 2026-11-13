<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { draftPrompt, resolveDraftPrompt } from './draft-protection'

const dialog = ref<HTMLDialogElement | null>(null)
watch(draftPrompt, async (prompt) => {
  if (!prompt) { dialog.value?.close(); return }
  await nextTick()
  if (draftPrompt.value === prompt && !dialog.value?.open) dialog.value?.showModal()
})
onBeforeUnmount(() => { resolveDraftPrompt(false); dialog.value?.close() })
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="draft-dialog cs-controls" aria-labelledby="draft-dialog-title" aria-describedby="draft-dialog-description" @cancel.prevent="resolveDraftPrompt(false)">
      <h2 id="draft-dialog-title">Descartar alterações?</h2>
      <p id="draft-dialog-description">Há alterações que ainda não foram enviadas. Permanecer conserva sua edição; descartar perde essas alterações e continua a navegação.</p>
      <ul><li v-for="label in draftPrompt?.labels" :key="label">{{ label }}</li></ul>
      <div class="actions">
        <button type="button" autofocus @click="resolveDraftPrompt(false)">Permanecer</button>
        <button type="button" @click="resolveDraftPrompt(true)">Descartar alterações</button>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.draft-dialog { width: min(100% - 32px, 520px); max-width: none; max-height: calc(100dvh - 32px); margin: auto; padding: var(--cs-space-24); border: 1px solid var(--cs-color-control-border); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); overflow-y: auto; overflow-wrap: anywhere; }
.draft-dialog::backdrop { background: rgb(8 27 32 / .55); }
h2 { margin: 0; font-size: var(--cs-type-24); font-weight: 600; line-height: 1.3; }
p, ul { margin-top: var(--cs-space-16); line-height: 1.5; }
ul { padding-inline-start: var(--cs-space-24); list-style: disc; }
.actions { display: flex; flex-wrap: wrap; gap: var(--cs-space-12); margin-top: var(--cs-space-24); }
.actions button { flex: 1 1 180px; }
</style>
