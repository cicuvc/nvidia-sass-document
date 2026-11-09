<script setup>
import { computed } from 'vue'

const props = defineProps({
  encoding: { type: Array, default: () => [] },
  selectedField: { type: Number, default: -1 },
})

const emit = defineEmits(['select-field'])

function hueFor(name) {
  let hash = 0
  for (const char of name) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0
  return Math.abs(hash) % 360
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

function select(field) {
  emit('select-field', props.selectedField === field.index ? -1 : field.index)
}
</script>

<template>
  <div class="bit-map-wrap">
    <div class="bit-map-toolbar">
      <span>128-bit instruction word</span>
      <span>bit 127 → 0</span>
    </div>
    <div class="bit-map" role="img" aria-label="Instruction bit field map">
      <button
        v-for="cell in bits"
        :key="cell.bit"
        class="bit-cell"
        :class="{
          occupied: Boolean(cell.field),
          selected: cell.field && cell.field.index === selectedField,
          dimmed: selectedField >= 0 && (!cell.field || cell.field.index !== selectedField),
        }"
        :style="cell.field ? {
          '--field-hue': cell.field.hue,
          '--field-alpha': cell.field.index === selectedField ? 0.78 : 0.42,
        } : {}"
        :title="cell.field
          ? `${cell.field.name} · bit ${cell.bit} · ${cell.field.ranges.join(', ')}`
          : `unused · bit ${cell.bit}`"
        @click="cell.field && select(cell.field)"
      >
        {{ cell.bit % 8 === 0 ? cell.bit : '' }}
      </button>
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
        <span>{{ field.name }}</span>
        <small>{{ field.ranges.join(' + ') }}</small>
      </button>
    </div>
  </div>
</template>
