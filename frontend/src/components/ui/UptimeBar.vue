<script setup lang="ts">
import { computed } from 'vue'
import type { Sample } from '@/api'

// 24 小时可用性：每格 30 分钟，共 48 格
const props = withDefaults(defineProps<{ samples?: Sample[]; cells?: number }>(), {
  samples: () => [],
  cells: 48,
})

const bars = computed(() => {
  const span = (24 * 3600) / props.cells
  const now = Math.floor(Date.now() / 1000)
  return Array.from({ length: props.cells }, (_, i) => {
    const end = now - (props.cells - 1 - i) * span
    const inCell = props.samples.filter((x) => x.t > end - span && x.t <= end)
    if (!inCell.length) return 'none'
    return inCell.some((x) => x.s === 'unavailable') ? 'bad' : 'good'
  })
})
</script>

<template>
  <span class="uptime" title="近 24 小时，每格 30 分钟">
    <i v-for="(b, i) in bars" :key="i" :class="b" />
  </span>
</template>

<style scoped>
.uptime {
  display: inline-flex;
  gap: 2px;
  height: 18px;
  align-items: stretch;
}

i {
  flex: none;
  width: 3px;
  border-radius: 1px;
  background: var(--border);
}

i.good {
  background: var(--ok);
  opacity: 0.85;
}

i.bad {
  background: var(--err);
}
</style>
