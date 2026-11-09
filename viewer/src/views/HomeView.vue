<script setup>
import { computed, onMounted } from 'vue'
import { ensureManifest, viewerState } from '../lib/store'

const architectures = computed(() => viewerState.manifest?.architectures || [])
const totals = computed(() => {
  const instructions = architectures.value.reduce(
    (sum, arch) => sum + arch.counts.instructions, 0)
  const variants = architectures.value.reduce(
    (sum, arch) => sum + arch.counts.variants, 0)
  return { instructions, variants }
})

onMounted(ensureManifest)
</script>

<template>
  <main class="home-view">
    <section class="hero">
      <div class="eyebrow">Reverse-engineered NVIDIA instruction set</div>
      <h1>One reference for every SASS generation.</h1>
      <p>
        Browse encoding classes, modifier fields, pipe membership and the research
        notes behind every instruction. Pick an architecture from the header or
        start from the generation cards below.
      </p>
      <div class="hero-stats">
        <span><strong>{{ architectures.length }}</strong> architectures</span>
        <span><strong>{{ totals.instructions }}</strong> instruction pages</span>
        <span><strong>{{ totals.variants }}</strong> encoding classes</span>
      </div>
    </section>

    <section v-if="!architectures.length" class="loading-card">
      Loading instruction catalogs…
    </section>

    <section v-else class="arch-grid">
      <router-link
        v-for="arch in architectures"
        :key="arch.id"
        class="arch-card"
        :to="{ name: 'arch', params: { arch: arch.id } }"
      >
        <div class="arch-card-top">
          <span class="arch-canonical">{{ arch.canonical }}</span>
          <span class="arch-name">{{ arch.displayName }}</span>
        </div>
        <div class="arch-counts">
          <span>{{ arch.counts.instructions }} mnemonics</span>
          <span>{{ arch.counts.variants }} variants</span>
        </div>
        <div class="coverage-line">
          <span :style="{ width: `${(arch.counts.documented / arch.counts.instructions) * 100}%` }"></span>
        </div>
        <small>{{ arch.counts.documented }} with dedicated notes</small>
      </router-link>
    </section>
  </main>
</template>
