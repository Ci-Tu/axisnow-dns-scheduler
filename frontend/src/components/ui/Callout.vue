<script setup lang="ts">
// 带操作按钮的提示条：左侧说明文字，右侧一个动作
withDefaults(defineProps<{ type?: 'info' | 'warning' | 'error' }>(), { type: 'info' })
</script>

<template>
  <div class="callout" :class="type">
    <div class="text"><slot /></div>
    <div v-if="$slots.action" class="action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.callout {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  border-radius: 6px;
  border: 1px solid;
  --c: var(--accent);
  border-color: color-mix(in srgb, var(--c) 30%, var(--border));
  background: color-mix(in srgb, var(--c) 7%, var(--surface));
}

.callout.warning {
  --c: var(--warn);
}

.callout.error {
  --c: var(--err);
}

.text {
  flex: 1;
  color: var(--text);
}

.action {
  flex: none;
}
</style>
