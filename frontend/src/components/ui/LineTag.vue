<script setup lang="ts">
import RegionFlag from './RegionFlag.vue'

// 线路标签：境内 → 中国国旗，境外/默认 → 地球
defineProps<{ label: string; region?: string | null }>()
</script>

<template>
  <span class="line-tag">
    <RegionFlag :code="region" :size="12" :title="label" />
    <span>{{ label }}</span>
  </span>
</template>

<style scoped>
.line-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  white-space: nowrap;
}
</style>
