<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QuickSearch from './components/QuickSearch.vue'
import { REPO_URL } from './config'
import { ensureManifest, viewerState } from './lib/store'

const route = useRoute()
const router = useRouter()
const error = ref('')

const architectures = computed(() => viewerState.manifest?.architectures || [])
const selectedArch = computed(() => String(route.params.arch || ''))

onMounted(async () => {
  try {
    await ensureManifest()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }
})

function changeArchitecture(event) {
  const arch = event.target.value
  if (arch) router.push({ name: 'arch', params: { arch } })
  else router.push({ name: 'home' })
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <router-link class="brand" :to="{ name: 'home' }">
        <span class="brand-mark">SASS</span>
        <span class="brand-copy">
          <strong>NVIDIA ISA</strong>
          <small>encoding reference</small>
        </span>
      </router-link>

      <QuickSearch class="header-search" />

      <div class="header-actions">
        <label class="arch-picker">
          <span>Architecture</span>
          <select :value="selectedArch" @change="changeArchitecture">
            <option value="">Select version</option>
            <option v-for="arch in architectures" :key="arch.id" :value="arch.id">
              {{ arch.canonical }} · {{ arch.displayName }}
            </option>
          </select>
        </label>
        <a class="repo-link" :href="REPO_URL" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </div>
    </header>

    <div v-if="error || viewerState.error" class="global-error">
      Failed to load viewer data: {{ error || viewerState.error }}
    </div>

    <router-view />
  </div>
</template>
