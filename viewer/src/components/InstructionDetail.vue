<script setup>
import { computed, ref, watch } from 'vue'
import { githubFileUrl } from '../config'
import { renderMarkdown } from '../lib/markdown'
import { loadInstruction } from '../lib/store'
import BitFieldMap from './BitFieldMap.vue'

const props = defineProps({
  arch: { type: String, required: true },
  slug: { type: String, required: true },
})

const detail = ref(null)
const error = ref('')
const loading = ref(false)
const selectedVariantIndex = ref(0)
const selectedField = ref(-1)
const probe = ref('')

const selectedVariant = computed(() =>
  detail.value?.variants[selectedVariantIndex.value] || null)

const noteHtml = computed(() =>
  renderMarkdown(detail.value?.note?.markdown || '', detail.value?.note?.path || ''))

const sourceNoteUrl = computed(() =>
  githubFileUrl(detail.value?.note?.path || ''))

const sourceDatabaseUrl = computed(() =>
  githubFileUrl(detail.value?.source?.database || ''))

const probeResult = computed(() => {
  const digits = probe.value.replace(/0x/gi, '').replace(/[^0-9a-f]/gi, '')
  if (digits.length !== 32 || !detail.value) return null
  const word = BigInt(`0x${digits}`)
  const opcode = Number(((word >> 91n) & 1n) << 12n | (word & 0xfffn))
  return {
    opcode,
    matches: detail.value.variants.filter((variant) => variant.opcode === opcode),
  }
})

async function load() {
  loading.value = true
  error.value = ''
  selectedField.value = -1
  probe.value = ''
  try {
    detail.value = await loadInstruction(props.arch, props.slug)
    const defaultIndex = detail.value.variants.findIndex((variant) => !variant.alternate)
    selectedVariantIndex.value = defaultIndex >= 0 ? defaultIndex : 0
  } catch (cause) {
    detail.value = null
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

function chooseProbeVariant(variant) {
  const index = detail.value?.variants.indexOf(variant) ?? -1
  if (index >= 0) selectedVariantIndex.value = index
}

watch(() => [props.arch, props.slug], load, { immediate: true })
</script>

<template>
  <div v-if="loading" class="center-state">Loading {{ slug.toUpperCase() }}…</div>
  <div v-else-if="error" class="center-state">
    <h1>Unable to load instruction</h1>
    <p>{{ error }}</p>
  </div>
  <article v-else-if="detail" class="instruction-detail">
    <header class="instruction-header">
      <div>
        <div class="eyebrow">{{ detail.arch }} · instruction reference</div>
        <h1>{{ detail.summary.mnemonic }}</h1>
        <p>{{ detail.summary.title }}</p>
      </div>
      <div class="header-links">
        <a v-if="detail.note" :href="sourceNoteUrl" target="_blank" rel="noreferrer">
          Source note ↗
        </a>
        <a :href="sourceDatabaseUrl" target="_blank" rel="noreferrer">ISA JSON ↗</a>
      </div>
    </header>

    <section class="quick-facts">
      <div class="fact">
        <span>Pipe</span>
        <strong>{{ detail.summary.pipe.join(', ') || '—' }}</strong>
      </div>
      <div class="fact">
        <span>Classes</span>
        <strong>{{ detail.variants.length }}</strong>
      </div>
      <div class="fact">
        <span>Opcode</span>
        <strong>{{ selectedVariant?.opcode == null ? '—' : `0x${selectedVariant.opcode.toString(16)}` }}</strong>
      </div>
      <div class="fact evidence-fact">
        <span>Evidence</span>
        <strong>{{ detail.note?.evidence || 'not documented' }}</strong>
        <small v-if="detail.note?.confidence">{{ detail.note.confidence }} confidence</small>
      </div>
    </section>

    <div v-if="!detail.note" class="notice">
      This mnemonic exists in the ISA database but does not have a dedicated
      instruction note yet.
    </div>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <span class="panel-kicker">Encoding</span>
          <h2>128-bit field map</h2>
        </div>
        <label class="variant-select">
          <span>Variant</span>
          <select v-model.number="selectedVariantIndex">
            <option
              v-for="(variant, index) in detail.variants"
              :key="variant.class"
              :value="index"
            >
              {{ variant.class }}{{ variant.alternate ? ' [ALT]' : '' }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="selectedVariant" class="variant-summary">
        <span>{{ selectedVariant.class }}</span>
        <span v-if="selectedVariant.alternate">ALTERNATE CLASS</span>
        <span v-if="selectedVariant.pipeSuffix">{{ selectedVariant.pipeSuffix }}</span>
      </div>

      <BitFieldMap
        v-if="selectedVariant"
        :encoding="selectedVariant.encoding"
        :selected-field="selectedField"
        @select-field="selectedField = $event"
      />
    </section>

    <section v-if="selectedVariant" class="panel">
      <div class="panel-heading">
        <div>
          <span class="panel-kicker">Selected CLASS</span>
          <h2>{{ selectedVariant.class }}</h2>
        </div>
        <span v-if="selectedVariant.opcode != null" class="opcode-badge">
          0x{{ selectedVariant.opcode.toString(16) }}
        </span>
      </div>
      <pre class="format-preview">{{ selectedVariant.format }}</pre>
      <div class="field-table-wrap">
        <table class="data-table">
          <thead>
            <tr><th>Bits</th><th>Field</th><th>Width</th><th>Source</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="(field, index) in selectedVariant.encoding"
              :key="`${index}:${field.name}`"
              :class="{ highlighted: selectedField === index }"
              @click="selectedField = selectedField === index ? -1 : index"
            >
              <td class="mono">
                {{ field.targets.map(([hi, lo]) => hi === lo ? `${hi}` : `${hi}:${lo}`).join(' + ') }}
              </td>
              <td class="mono">{{ field.name }}</td>
              <td>{{ field.width }}</td>
              <td class="mono">{{ field.rhs }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel probe-panel">
      <div>
        <span class="panel-kicker">Encoding lookup</span>
        <h2>Check a 128-bit word</h2>
        <p>Paste hi64 + lo64 as 32 hexadecimal digits. Only opcode candidates are matched in this initial version.</p>
      </div>
      <input
        v-model="probe"
        class="probe-input"
        spellcheck="false"
        autocomplete="off"
        placeholder="000fe400078e0202 001b1c7824"
      />
      <div v-if="probeResult" class="probe-result">
        <span>Opcode <code>0x{{ probeResult.opcode.toString(16) }}</code></span>
        <template v-if="probeResult.matches.length">
          <button
            v-for="variant in probeResult.matches"
            :key="variant.class"
            @click="chooseProbeVariant(variant)"
          >
            {{ variant.class }}
          </button>
        </template>
        <span v-else>No matching class for this instruction.</span>
      </div>
    </section>

    <section v-if="detail.note" class="panel notes-panel">
      <div class="panel-heading">
        <div>
          <span class="panel-kicker">Research note</span>
          <h2>{{ detail.note.title }}</h2>
        </div>
        <div class="note-badges">
          <span v-if="detail.note.status">{{ detail.note.status }}</span>
          <span v-if="detail.note.evidence">{{ detail.note.evidence }}</span>
        </div>
      </div>
      <div class="markdown-body" v-html="noteHtml"></div>
    </section>
  </article>
</template>
