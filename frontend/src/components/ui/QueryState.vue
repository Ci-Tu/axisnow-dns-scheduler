<script setup lang="ts">
import { NButton, NResult, NSkeleton } from 'naive-ui'
import { useRouter } from 'vue-router'

// 统一的「加载中 / 出错 / 有数据」三态外壳
const props = defineProps<{ loading: boolean; error: string; hasData: boolean; rows?: number }>()
const emit = defineEmits<{ retry: [] }>()
const router = useRouter()

const needsToken = () => props.error.includes('API Token')
</script>

<template>
  <slot v-if="hasData" />
  <div v-else-if="loading" class="skeleton">
    <NSkeleton text :repeat="rows ?? 4" />
  </div>
  <NResult v-else-if="error" status="warning" title="数据读取失败" :description="error" size="small">
    <template #footer>
      <NButton v-if="needsToken()" type="primary" @click="router.push('/settings')">
        去设置 API Token
      </NButton>
      <NButton v-else @click="emit('retry')">重试</NButton>
    </template>
  </NResult>
</template>

<style scoped>
.skeleton {
  padding: 8px 0;
}
</style>
