<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ status?: string | null; label?: boolean }>(), {
  status: null,
  label: false,
})

const info = computed(() => {
  switch (props.status) {
    case 'available':
      return { cls: 'ok', text: '可用' }
    case 'unavailable':
      return { cls: 'err', text: '不可用' }
    case null:
    case undefined:
    case '':
      return { cls: 'idle', text: '未监控' }
    default:
      return { cls: 'idle', text: '检测中' }
  }
})
</script>

<template>
  <span class="status" :class="info.cls" :title="info.text">
    <i />
    <span v-if="label">{{ info.text }}</span>
  </span>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-2);
  white-space: nowrap;
}

i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  background: var(--idle);
}

.ok i {
  background: var(--ok);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 18%, transparent);
}

.err i {
  background: var(--err);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--err) 18%, transparent);
}

.err {
  color: var(--err);
}
</style>
