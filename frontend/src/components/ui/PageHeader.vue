<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <header class="page-header">
    <div class="text">
      <slot name="before-title" />
      <h1>{{ title }}</h1>
      <p v-if="description || $slots.description" class="desc">
        <slot name="description">{{ description }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.text {
  flex: 1;
  min-width: 240px;
}

h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.desc {
  margin: 4px 0 0;
  color: var(--text-3);
  max-width: 72ch;
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
