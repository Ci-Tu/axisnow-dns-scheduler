<script setup lang="ts">
import { computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { GripVertical } from 'lucide-vue-next'
import type { IpView } from '@/api'
import IpBadge from '@/components/ui/IpBadge.vue'

// 拖动调整 IP 优先级：排在最前面的优先级最高
const props = defineProps<{ modelValue: string[]; items: IpView[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string[]] }>()

const byIp = computed(() => new Map(props.items.map((i) => [i.ip, i])))

const list = computed({
  get: () =>
    props.modelValue.map(
      (ip) =>
        byIp.value.get(ip) ?? {
          ip,
          name: '',
          note: '',
          probe: null,
          geo: { country: null, asn: null, org: null, private: false },
        },
    ),
  set: (v: IpView[]) => emit('update:modelValue', v.map((i) => i.ip)),
})
</script>

<template>
  <VueDraggable
    v-model="list"
    class="order"
    :animation="150"
    :disabled="disabled"
    ghost-class="ghost"
    handle=".handle"
  >
    <div v-for="(item, i) in list" :key="item.ip" class="cell" :class="{ disabled }">
      <GripVertical v-if="!disabled" :size="13" class="handle" />
      <IpBadge :item="item" :rank="i + 1" />
    </div>
  </VueDraggable>
</template>

<style scoped>
.order {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.handle {
  color: var(--text-3);
  cursor: grab;
}

.cell:hover .handle {
  color: var(--text);
}

.ghost {
  opacity: 0.4;
}
</style>
