<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputGroup,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
} from 'naive-ui'
import { api, type Options } from '@/api'
import { useAction } from '@/composables/useAction'
import { invalidate } from '@/composables/useResource'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [boolean]; created: [domain: string] }>()

const { run, pending } = useAction()
const opts = ref<Options | null>(null)
const loadError = ref('')
const checkResult = ref<string | null>(null)

const form = reactive({
  mode: 'managed' as 'managed' | 'self',
  prefix: '',
  zone: '',
  domain: '',
  provider: '',
  recordType: 'A',
  name: '',
})

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    checkResult.value = null
    try {
      opts.value = await api.options()
      loadError.value = ''
      form.zone ||= zones.value[0]?.value ?? ''
      form.provider ||= selfProviders.value[0]?.value ?? ''
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : String(e)
    }
  },
)

const zones = computed(() =>
  (opts.value?.managed_providers ?? []).flatMap((p) =>
    p.zones.map((z) => ({ value: z.name, label: `${z.name}（${p.type}）`, provider: p.uuid, zone: z.uuid })),
  ),
)
const selfProviders = computed(() =>
  (opts.value?.providers ?? [])
    .filter((p) => !p.managed && p.source !== 'platform')
    .map((p) => ({ value: p.uuid, label: `${p.name} · ${p.type}` })),
)

function target(): Record<string, unknown> {
  if (form.mode === 'managed') {
    const z = zones.value.find((x) => x.value === form.zone)
    return {
      mode: 'managed',
      prefix: form.prefix.trim().toLowerCase(),
      zone: form.zone,
      dns_provider_uuid: z?.provider,
      dns_zone_uuid: z?.zone,
      record_type: form.recordType,
    }
  }
  return {
    mode: 'self',
    domain: form.domain.trim().toLowerCase(),
    dns_provider_uuid: form.provider,
    record_type: form.recordType,
  }
}

const fullDomain = computed(() =>
  form.mode === 'managed' ? `${form.prefix.trim() || '…'}.${form.zone}` : form.domain.trim(),
)

async function check() {
  const t = target()
  const r = await run('check', () =>
    api.domains.checkRecords({
      domain: form.mode === 'managed' ? `${t.prefix}.${t.zone}` : t.domain,
      dns_provider_uuid: t.dns_provider_uuid,
      record_type: t.record_type,
    }),
  )
  if (r) checkResult.value = JSON.stringify(r.result, null, 2)
}

async function submit() {
  const r = await run('create', () => api.domains.create({ ...target(), name: form.name.trim() }),
    '调度域已创建')
  if (r) {
    invalidate('domains', 'dashboard', 'rules')
    emit('update:show', false)
    emit('created', r.domain.domain)
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="新建调度域"
    style="width: 620px; max-width: calc(100vw - 32px)"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <NAlert v-if="loadError" type="error" :show-icon="false">{{ loadError }}</NAlert>
    <NSpin v-else-if="!opts" size="small" class="loading" />
    <NForm v-else label-placement="top" :show-feedback="false" class="form">
      <NFormItem label="托管方式">
        <NRadioGroup v-model:value="form.mode">
          <NRadioButton value="managed">AxisNow 托管</NRadioButton>
          <NRadioButton value="self">自托管</NRadioButton>
        </NRadioGroup>
      </NFormItem>
      <p class="muted small hint">
        <template v-if="form.mode === 'managed'">
          由 AxisNow 提供调度域和 DNS，无需配置 DNS 集成，并且支持境内 / 境外分流。
        </template>
        <template v-else>
          使用你自己的 DNS 服务商。注意 Cloudflare 只有「默认」线路，做不到分线路解析。
        </template>
      </p>

      <NFormItem v-if="form.mode === 'managed'" label="子域名">
        <NInputGroup>
          <NInput v-model:value="form.prefix" placeholder="hub" style="flex: 1" />
          <NSelect v-model:value="form.zone" :options="zones" style="width: 260px"
            placeholder="托管后缀" />
        </NInputGroup>
      </NFormItem>
      <template v-else>
        <NFormItem label="完整域名">
          <NInput v-model:value="form.domain" placeholder="edge.example.com" />
        </NFormItem>
        <NFormItem label="DNS 服务商">
          <NSelect v-model:value="form.provider" :options="selfProviders"
            placeholder="账号下还没有自建 DNS 服务商" />
        </NFormItem>
      </template>

      <div class="grid-2">
        <NFormItem label="记录类型">
          <NRadioGroup v-model:value="form.recordType">
            <NRadioButton value="A">A</NRadioButton>
            <NRadioButton value="CNAME">CNAME</NRadioButton>
          </NRadioGroup>
        </NFormItem>
        <NFormItem label="备注名称（可选）">
          <NInput v-model:value="form.name" maxlength="100" />
        </NFormItem>
      </div>

      <NAlert type="info" :show-icon="false">
        将创建 <code>{{ fullDomain }}</code>。创建后还需要在你自己的 DNS 上把业务域名 CNAME
        到它，解析才会生效；配好 Cloudflare Token 后可以在列表里一键完成。
      </NAlert>
      <pre v-if="checkResult" class="code check">{{ checkResult }}</pre>
    </NForm>

    <template #footer>
      <div class="row">
        <NButton :loading="pending === 'check'" :disabled="!opts" @click="check">预检冲突记录</NButton>
        <span class="spacer" />
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton type="primary" :loading="pending === 'create'" :disabled="!opts" @click="submit">
          创建
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

.hint {
  margin: -6px 0 14px;
}

.check {
  margin-top: 12px;
  max-height: 200px;
}
</style>
