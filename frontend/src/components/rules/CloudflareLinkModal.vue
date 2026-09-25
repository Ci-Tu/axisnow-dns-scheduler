<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputGroup,
  NInputGroupLabel,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
  NTag,
} from 'naive-ui'
import Callout from '@/components/ui/Callout.vue'
import { api, type CfRecord, type CfZone } from '@/api'
import { useAction } from '@/composables/useAction'
import { invalidate } from '@/composables/useResource'

// 在自己的 Cloudflare 上创建一条指向 AxisNow 调度域的记录（强制仅 DNS）
const props = defineProps<{ show: boolean; target: string }>()
const emit = defineEmits<{ 'update:show': [boolean] }>()

const router = useRouter()
const { run, pending } = useAction()
const state = ref<'loading' | 'no-token' | 'error' | 'ready'>('loading')
const error = ref('')
const zones = ref<CfZone[]>([])
const linked = ref<CfRecord[]>([])
const zoneId = ref('')
const prefix = ref('')
const ttl = ref(1)

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    state.value = 'loading'
    prefix.value = ''
    try {
      const status = await api.cloudflare.status()
      if (!status.token.configured) {
        state.value = 'no-token'
        return
      }
      zones.value = (await api.cloudflare.zones()).zones
      zoneId.value = zones.value[0]?.id ?? ''
      state.value = 'ready'
      linked.value = (await api.cloudflare.linked(props.target).catch(() => ({ records: [] }))).records
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      state.value = 'error'
    }
  },
)

const zoneName = computed(() => zones.value.find((z) => z.id === zoneId.value)?.name ?? '')
const zoneOptions = computed(() =>
  zones.value.map((z) => ({ value: z.id, label: z.status === 'active' ? z.name : `${z.name}（${z.status}）` })),
)
const fullName = computed(() => {
  const p = prefix.value.trim().replace(/\.$/, '')
  if (!p || p === '@') return zoneName.value
  return p.endsWith(`.${zoneName.value}`) ? p : `${p}.${zoneName.value}`
})

async function submit() {
  const r = await run(
    'create',
    () =>
      api.cloudflare.createRecord({
        zone_id: zoneId.value,
        name: fullName.value,
        content: props.target,
        type: 'CNAME',
        ttl: ttl.value,
      }),
    (res) => `已创建 ${res.record.name} → ${props.target}`,
  )
  if (r) {
    invalidate('cloudflare')
    emit('update:show', false)
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="接入 Cloudflare"
    style="width: 580px; max-width: calc(100vw - 32px)"
    @update:show="emit('update:show', $event)"
  >
    <NSpin v-if="state === 'loading'" size="small" class="loading" />
    <Callout v-else-if="state === 'no-token'" type="info">
      还没有配置 Cloudflare API Token。
      <template #action>
        <NButton size="small" @click="router.push('/cloudflare')">去配置</NButton>
      </template>
    </Callout>
    <NAlert v-else-if="state === 'error'" type="error" :show-icon="false">{{ error }}</NAlert>
    <NForm v-else label-placement="top" :show-feedback="false" class="form">
      <p class="muted small intro">
        在你的 Cloudflare 上创建一条 CNAME，指向调度域 <code>{{ target }}</code>。
      </p>
      <NFormItem label="Cloudflare 域名（Zone）">
        <NSelect v-model:value="zoneId" :options="zoneOptions" />
      </NFormItem>
      <NFormItem label="记录名">
        <NInputGroup>
          <NInput v-model:value="prefix" placeholder="例如 www，留空或 @ 表示根域" />
          <NInputGroupLabel>.{{ zoneName }}</NInputGroupLabel>
        </NInputGroup>
      </NFormItem>
      <NFormItem label="TTL">
        <NRadioGroup v-model:value="ttl">
          <NRadioButton :value="1">自动</NRadioButton>
          <NRadioButton :value="60">1 分钟</NRadioButton>
          <NRadioButton :value="600">10 分钟</NRadioButton>
        </NRadioGroup>
      </NFormItem>
      <NAlert type="warning" :show-icon="false">
        记录以<b>仅 DNS</b>（不经过 Cloudflare 代理）创建。开启代理后访客拿到的是 Cloudflare
        的 IP，AxisNow 的按线路调度会完全失效。
      </NAlert>

      <div v-if="linked.length" class="linked">
        <div class="small muted">已经指向该调度域的记录</div>
        <div v-for="r in linked" :key="r.id" class="row">
          <span class="mono">{{ r.name }}</span>
          <NTag size="small" :bordered="false">{{ r.type }}</NTag>
          <NTag v-if="r.proxied" size="small" type="error" :bordered="false">已开代理，调度失效</NTag>
        </div>
      </div>
    </NForm>

    <template #footer>
      <div class="row">
        <span class="spacer" />
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton
          v-if="state === 'ready'"
          type="primary"
          :loading="pending === 'create'"
          :disabled="!zoneId"
          @click="submit"
        >
          创建 {{ fullName }}
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.loading {
  display: flex;
  justify-content: center;
  padding: 40px;
}

.form :deep(.n-form-item) {
  margin-bottom: 14px;
}

.intro {
  margin: 0 0 14px;
}

.linked {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
