<script setup lang="ts">
import { isIdentityVerified, knownJobs, knownJobsNotice, sessionRole } from '../account/session'
</script>

<template>
  <section v-if="isIdentityVerified && sessionRole === 'admin' && (knownJobs.generation || knownJobs.training || knownJobsNotice)" class="resume-links cs-controls" aria-label="Retomar trabalhos conhecidos">
    <p>Trabalhos conhecidos nesta aba. Retomar consulta o acompanhamento; não inicia uma nova execução.</p>
    <nav aria-label="Links de retomada">
      <RouterLink v-if="knownJobs.generation" :to="{ path: '/laboratory', query: { job: knownJobs.generation.jobId } }">Retomar geração</RouterLink>
      <RouterLink v-if="knownJobs.training" :to="{ path: '/training', query: { job: knownJobs.training.jobId, dataset: knownJobs.training.datasetId } }">Retomar treinamento</RouterLink>
    </nav>
    <p v-if="knownJobsNotice" role="status">{{ knownJobsNotice }}</p>
  </section>
</template>

<style scoped>
.resume-links { margin-block: var(--cs-space-16); padding: var(--cs-space-16); border: 1px solid var(--cs-color-line); border-radius: var(--cs-radius-8); background: var(--cs-color-surface); color: var(--cs-color-ink); overflow-wrap: anywhere; }
p { margin: 0; font-size: var(--cs-type-14); line-height: 1.5; }
nav { display: flex; flex-wrap: wrap; gap: var(--cs-space-8) var(--cs-space-24); margin-top: var(--cs-space-8); }
a { display: inline-flex; align-items: center; min-height: var(--cs-control-min-height); color: var(--cs-color-accent); text-decoration: underline; text-underline-offset: .2em; }
[role='status'] { margin-top: var(--cs-space-8); }
</style>
