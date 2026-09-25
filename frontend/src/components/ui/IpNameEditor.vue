<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NInput, NPopover } from 'naive-ui'
import { Pencil } from 'lucide-vue-next'
import { api } from '@/api'
import { useAction } from '@/composables/useAction'
import { invalidate } from '@/composables/useResource'

// 给 IP 起一个全局名称（所有页面共用），例如「东京 · Oracle」
const props = defineProps<{ ip: string; name: string }>()
const emit = defineEmits<{ saved: [name: string] }>()

const { run, pending } = useAction()
const show = ref(false)
const value = ref('')

function open(v: boolean) {
  show.value = v
  if (v) value.value = props.name
}

async function save() {
  const ok = await run('save', () => api.setIpLabel(props.ip, value.value.trim()), '名称已保存')
  if (ok !== undefined) {
    show.value = false
    invalidate('dashboard', 'rules', 'domains', 'probe')
    emit('saved', value.value.trim())
  }
}
</script>

<template>
  <NPopover trigger="click" :show="show" placement="bottom-start" @update:show="open">
    <template #trigger>
      <NButton quaternary size="tiny" circle :title="`为 ${ip} 命名`">
        <Pencil :size="12" />
      </NButton>
    </template>
    <div class="editor">
      <div class="small muted">{{ ip }} 的名称（所有页面共用，留空则删除）</div>
      <NInput v-model:value="value" size="small" maxlength="40" placeholder="例如 东京 · Oracle"
        @keyup.enter="save" />
      <div class="row">
        <span class="spacer" />
        <NButton size="small" @click="show = false">取消</NButton>
        <NButton size="small" type="primary" :loading="pending === 'save'" @click="save">保存</NButton>
      </div>
    </div>
  </NPopover>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 260px;
}
</style>
