<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ensureManifest, viewerState } from '../lib/store'

const router = useRouter()
const route = useRoute()
const query = ref('')
const open = ref(false)
const focused = ref(-1)
const input = ref(null)
const root = ref(null)

const architectures = computed(() => viewerState.manifest?.architectures || [])

function searchableOpcode(value) {
  const text = String(value || '').toLowerCase()
  const probe = query.value.trim().toLowerCase()
  return probe.startsWith('0x') ? text === probe : text.includes(probe)
}

const results = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return []
  const scored = []
  for (const arch of architectures.value) {
    for (const instruction of arch.instructions) {
      const mnemonic = instruction.mnemonic.toLowerCase()
      const title = instruction.title.toLowerCase()
      let score = 0
      if (mnemonic === needle) score = 120
      else if (instruction.opcodes.some(searchableOpcode)) score = 110
      else if (mnemonic.startsWith(needle)) score = 90
      else if (instruction.classes.some((name) => name.toLowerCase().includes(needle))) score = 80
      else if (mnemonic.includes(needle)) score = 70
      else if (title.includes(needle)) score = 60
      else if (instruction.pipe.some((pipe) => pipe.toLowerCase().includes(needle))) score = 45
      if (score) scored.push({ score, arch, instruction })
    }
  }
  return scored
    .sort((a, b) =>
      b.score - a.score ||
      a.instruction.mnemonic.localeCompare(b.instruction.mnemonic) ||
      a.arch.id.localeCompare(b.arch.id)
    )
    .slice(0, 18)
})

function focusSearch(event) {
  const isShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k'
  if (!isShortcut) return
  event.preventDefault()
  open.value = true
  nextTick(() => input.value?.focus())
}

function closeOnOutsideClick(event) {
  if (open.value && root.value && !root.value.contains(event.target)) {
    open.value = false
  }
}

function choose(entry) {
  if (!entry) return
  router.push({
    name: 'arch',
    params: { arch: entry.arch.id, slug: entry.instruction.slug },
  })
  query.value = ''
  open.value = false
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    open.value = false
    input.value?.blur()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    focused.value = Math.min(focused.value + 1, results.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    focused.value = Math.max(focused.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    choose(results.value[focused.value] || results.value[0])
  }
}

watch(query, () => {
  focused.value = results.value.length ? 0 : -1
  open.value = Boolean(query.value.trim())
})

watch(() => route.fullPath, () => {
  open.value = false
})

onMounted(() => {
  ensureManifest()
  document.addEventListener('keydown', focusSearch)
  document.addEventListener('pointerdown', closeOnOutsideClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', focusSearch)
  document.removeEventListener('pointerdown', closeOnOutsideClick)
})
</script>

<template>
  <div ref="root" class="quick-search">
    <div class="search-field">
      <span class="search-icon">⌕</span>
      <input
        ref="input"
        v-model="query"
        type="search"
        autocomplete="off"
        spellcheck="false"
        placeholder="Search IMAD, 0x224, LOP3..."
        aria-label="Search instructions"
        @focus="open = Boolean(query.trim())"
        @keydown="onKeydown"
      />
      <kbd>Ctrl K</kbd>
    </div>

    <div v-if="open" class="search-popover">
      <div v-if="!results.length" class="search-empty">
        No instruction matched “{{ query }}”.
      </div>
      <button
        v-for="(entry, index) in results"
        :key="entry.instruction.id"
        class="search-result"
        :class="{ focused: index === focused }"
        @mousedown.prevent="choose(entry)"
        @mouseenter="focused = index"
      >
        <span class="result-main">
          <strong>{{ entry.instruction.mnemonic }}</strong>
          <span>{{ entry.instruction.title.replace(entry.instruction.mnemonic, '').replace(/^[\s—-]+/, '') }}</span>
        </span>
        <span class="result-meta">
          <span>{{ entry.arch.canonical }}</span>
          <span v-if="entry.instruction.opcodes.length">
            {{ entry.instruction.opcodes.slice(0, 2).join(' / ') }}
          </span>
        </span>
      </button>
      <div class="search-footer">
        <span>↑↓ navigate</span>
        <span>Enter open</span>
        <span>Esc close</span>
      </div>
    </div>
  </div>
</template>
