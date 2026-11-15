<script setup>
import { computed } from 'vue'

const props = defineProps({
  encoding: { type: Array, default: () => [] },
  selectedField: { type: Number, default: -1 },
  opcode: { type: Number, default: null },
})

const emit = defineEmits(['select-field'])

const FIELD_HUES = [205, 142, 30, 280, 0, 185, 55, 320, 105, 250, 15, 165]

function hueFor(name) {
  let hash = 0
  for (const char of name) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0
  const base = FIELD_HUES[Math.abs(hash) % FIELD_HUES.length]
  const offset = ((Math.abs(hash) >> 8) % 11) - 5
  return (base + offset + 360) % 360
}

const fields = computed(() =>
  props.encoding.map((field, index) => ({
    ...field,
    index,
    hue: hueFor(field.name || String(index)),
    ranges: field.targets.map(([hi, lo]) => (hi === lo ? `${hi}` : `${hi}:${lo}`)),
  }))
)

const bits = computed(() => {
  const map = new Map()
  for (const field of fields.value) {
    for (const [hi, lo] of field.targets) {
      for (let bit = lo; bit <= hi; bit += 1) map.set(bit, field)
    }
  }
  return Array.from({ length: 128 }, (_, index) => {
    const bit = 127 - index
    return { bit, field: map.get(bit) || null }
  })
})

const rows = computed(() =>
  Array.from({ length: 4 }, (_, row) => bits.value.slice(row * 32, row * 32 + 32)))

function opcodeBit(field, bit) {
  if (!field || field.rhs_kind !== 'opcode' || props.opcode == null) return null
  let consumed = 0
  for (const [hi, lo] of field.targets) {
    const width = hi - lo + 1
    if (bit >= lo && bit <= hi) {
      const shift = field.width - consumed - width + (bit - lo)
      return (props.opcode >> shift) & 1
    }
    consumed += width
  }
  return null
}

function select(field) {
  emit('select-field', props.selectedField === field.index ? -1 : field.index)
}
</script>

<template>
  <div class="bit-map-wrap">
    <div class="bit-map-toolbar">
      <span>128-bit instruction word</span>
      <span>0/1 = fixed opcode bit</span>
    </div>
    <div class="bit-map" role="img" aria-label="Instruction bit field map">
      <div v-for="row in rows" :key="row[0].bit" class="bit-row">
        <span class="bit-boundary">{{ row[0].bit }}</span>
        <div class="bit-cells">
          <button
            v-for="cell in row"
            :key="cell.bit"
            class="bit-cell"
            :class="{
              occupied: Boolean(cell.field),
              selected: cell.field && cell.field.index === selectedField,
              dimmed: selectedField >= 0 && (!cell.field || cell.field.index !== selectedField),
            }"
            :style="cell.field ? {
              '--field-hue': cell.field.hue,
              '--field-alpha': cell.field.index === selectedField ? 0.82 : 0.52,
            } : {}"
            :aria-label="cell.field
              ? `${cell.field.friendlyName || cell.field.name}, bit ${cell.bit}${opcodeBit(cell.field, cell.bit) == null ? '' : `, fixed ${opcodeBit(cell.field, cell.bit)}`}`
              : `unused, bit ${cell.bit}`"
            :title="cell.field
              ? `${cell.field.friendlyName || cell.field.name} · bit ${cell.bit} · ${cell.field.ranges.join(', ')}${opcodeBit(cell.field, cell.bit) == null ? '' : ` · fixed ${opcodeBit(cell.field, cell.bit)}`}`
              : `unused · bit ${cell.bit}`"
            @click="cell.field && select(cell.field)"
          >
            <span v-if="opcodeBit(cell.field, cell.bit) != null" class="fixed-bit">
              {{ opcodeBit(cell.field, cell.bit) }}
            </span>
          </button>
        </div>
        <span class="bit-boundary">{{ row[row.length - 1].bit }}</span>
      </div>
    </div>

    <div class="field-legend">
      <button
        v-for="field in fields"
        :key="`${field.index}:${field.name}`"
        class="field-chip"
        :class="{ selected: field.index === selectedField }"
        :style="{ '--field-hue': field.hue }"
        @click="select(field)"
      >
        <span>{{ field.friendlyName || field.name }}</span>
        <small>
          {{ field.friendlyName ? `${field.name} · ` : '' }}{{ field.ranges.join(' + ') }}
        </small>
      </button>
    </div>
  </div>
</template>
