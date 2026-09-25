<script setup lang="ts">
import { computed } from 'vue'
import { Globe } from 'lucide-vue-next'
import { countryName } from '@/utils/countries'

// code：ISO 3166 两位码（小写）→ SVG 国旗；"world" → 地球图标；空 → 占位
const props = withDefaults(defineProps<{ code?: string | null; size?: number; title?: string }>(), {
  code: null,
  size: 14,
  title: undefined,
})

const kind = computed(() => {
  if (!props.code) return 'none'
  if (props.code === 'world') return 'world'
  return /^[a-z]{2}$/.test(props.code) ? 'flag' : 'none'
})

const label = computed(() => {
  if (props.title) return props.title
  if (kind.value === 'world') return '全球'
  if (kind.value === 'flag') return countryName(props.code!)
  return '未知地区'
})
</script>

<template>
  <span class="region-flag" :title="label" :style="{ '--h': `${size}px` }">
    <span v-if="kind === 'flag'" :class="['fi', `fi-${code}`]" />
    <Globe v-else-if="kind === 'world'" :size="size" :stroke-width="1.8" class="globe" />
    <span v-else class="placeholder" />
  </span>
</template>

<style scoped>
.region-flag {
  display: inline-flex;
  align-items: center;
  flex: none;
  line-height: 1;
}

.fi {
  width: calc(var(--h) * 4 / 3);
  height: var(--h);
  border-radius: 2px;
  background-size: cover;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.08);
}

.globe {
  color: var(--text-3);
}

.placeholder {
  width: calc(var(--h) * 4 / 3);
  height: var(--h);
  border-radius: 2px;
  background: var(--border-soft);
  border: 1px dashed var(--border);
}
</style>
