<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InstructionDetail from '../components/InstructionDetail.vue'
import {
  ensureManifest,
  findArchitecture,
  viewerState,
} from '../lib/store'

const route = useRoute()
const router = useRouter()
const query = ref('')
const sidebarOpen = ref(false)
const sidebarMode = ref('alphabetical')

const manifestReady = computed(() => Boolean(viewerState.manifest))
const architecture = computed(() => findArchitecture(String(route.params.arch || '')))
const instructions = computed(() => architecture.value?.instructions || [])

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return instructions.value
  return instructions.value.filter((instruction) => {
    const opcodeHit = instruction.opcodes.some((opcode) =>
      opcode.toLowerCase().includes(needle.startsWith('0x') ? needle : `0x${needle}`))
    return (
      instruction.mnemonic.toLowerCase().includes(needle) ||
      instruction.title.toLowerCase().includes(needle) ||
      instruction.classes.some((name) => name.toLowerCase().includes(needle)) ||
      instruction.pipe.some((name) => name.toLowerCase().includes(needle)) ||
      opcodeHit
    )
  })
})

const groups = computed(() => {
  if (query.value.trim()) return [{ title: 'Results', items: filtered.value }]
  if (sidebarMode.value === 'pipe') {
    const buckets = new Map()
    for (const instruction of filtered.value) {
      const pipe = instruction.pipe[0] || 'unclassified'
      if (!buckets.has(pipe)) buckets.set(pipe, [])
      buckets.get(pipe).push(instruction)
    }
    return [...buckets.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([title, items]) => ({ title, items }))
  }
  const buckets = [
    ['A–C', /^[A-C]/],
    ['D–F', /^[D-F]/],
    ['G–J', /^[G-J]/],
    ['K–O', /^[K-O]/],
    ['P–S', /^[P-S]/],
    ['T–Z', /^[T-Z]/],
  ]
  const result = buckets.map(([title, regex]) => ({
    title,
    items: filtered.value.filter((instruction) => regex.test(instruction.mnemonic)),
  }))
  const other = filtered.value.filter((instruction) =>
    !buckets.some(([, regex]) => regex.test(instruction.mnemonic)))
  if (other.length) result.push({ title: 'Other', items: other })
  return result.filter((group) => group.items.length)
})

function selectInstruction(instruction) {
  sidebarOpen.value = false
  router.push({
    name: 'arch',
    params: { arch: route.params.arch, slug: instruction.slug },
  })
}

function onQueryKeydown(event) {
  if (event.key === 'Enter' && filtered.value[0]) {
    selectInstruction(filtered.value[0])
  }
}

onMounted(ensureManifest)
watch(() => route.params.arch, () => {
  query.value = ''
  sidebarOpen.value = false
})
</script>

<template>
  <main v-if="!manifestReady" class="center-state">Loading ISA catalog…</main>
  <main v-else-if="!architecture" class="center-state">
    <h1>Unknown architecture</h1>
    <p>No catalog exists for {{ route.params.arch }}.</p>
    <router-link class="button-link" :to="{ name: 'home' }">Back to overview</router-link>
  </main>
  <main v-else class="arch-layout">
    <button class="mobile-sidebar-toggle" @click="sidebarOpen = !sidebarOpen">
      {{ sidebarOpen ? 'Close' : 'Instructions' }}
    </button>

    <aside class="instruction-sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-heading">
        <div>
          <span class="eyebrow">{{ architecture.canonical }}</span>
          <h2>{{ architecture.displayName }}</h2>
        </div>
        <span class="sidebar-count">{{ filtered.length }}</span>
      </div>

      <input
        v-model="query"
        class="sidebar-search"
        type="search"
        autocomplete="off"
        spellcheck="false"
        placeholder="Filter mnemonic / opcode / pipe"
        @keydown="onQueryKeydown"
      />

      <div class="sidebar-tabs" role="tablist" aria-label="Instruction grouping">
        <button
          role="tab"
          :aria-selected="sidebarMode === 'alphabetical'"
          :class="{ active: sidebarMode === 'alphabetical' }"
          @click="sidebarMode = 'alphabetical'"
        >
          A–Z
        </button>
        <button
          role="tab"
          :aria-selected="sidebarMode === 'pipe'"
          :class="{ active: sidebarMode === 'pipe' }"
          @click="sidebarMode = 'pipe'"
        >
          Pipe
        </button>
      </div>

      <nav class="instruction-groups" aria-label="Instruction list">
        <section v-for="group in groups" :key="group.title" class="instruction-group">
          <h3>{{ group.title }}</h3>
          <button
            v-for="instruction in group.items"
            :key="instruction.id"
            class="instruction-link"
            :class="{ active: route.params.slug === instruction.slug }"
            @click="selectInstruction(instruction)"
          >
            <span>{{ instruction.mnemonic }}</span>
            <small>{{ instruction.opcodes[0] || `${instruction.variantCount} forms` }}</small>
          </button>
        </section>
        <p v-if="!filtered.length" class="sidebar-empty">No matching instruction.</p>
      </nav>
    </aside>

    <section class="main-pane">
      <InstructionDetail
        v-if="route.params.slug"
        :arch="architecture.id"
        :slug="String(route.params.slug)"
      />
      <div v-else class="arch-overview">
        <div class="eyebrow">{{ architecture.canonical }} · {{ architecture.displayName }}</div>
        <h1>Instruction catalog</h1>
        <p>
          Select an instruction from the sidebar. The catalog includes all parsed
          mnemonics, with dedicated research notes where available.
        </p>
        <div class="overview-stats">
          <div><strong>{{ architecture.counts.instructions }}</strong><span>mnemonics</span></div>
          <div><strong>{{ architecture.counts.documented }}</strong><span>documented</span></div>
          <div><strong>{{ architecture.counts.compute }}</strong><span>compute</span></div>
          <div><strong>{{ architecture.counts.variants }}</strong><span>CLASS variants</span></div>
        </div>
        <div class="overview-list">
          <button
            v-for="instruction in architecture.instructions.filter((item) => item.compute).slice(0, 40)"
            :key="instruction.id"
            class="overview-instruction"
            @click="selectInstruction(instruction)"
          >
            <strong>{{ instruction.mnemonic }}</strong>
            <span>{{ instruction.pipe.join(', ') || 'unknown pipe' }}</span>
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
