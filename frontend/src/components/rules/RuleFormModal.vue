<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
} from 'naive-ui'
import { api, type Domain, type Options, type PoolMode, type Rule } from '@/api'
import IpBadge from '@/components/ui/IpBadge.vue'
import { useAction } from '@/composables/useAction'
import { invalidate } from '@/composables/useResource'
import { geoSelectOptions, renderGeoLabel } from './geoOptions'

const props = defineProps<{
  show: boolean
  rule?: Rule | null // 有值 = 编辑
  domains?: Domain[] // 新建时可选的调度域
  domainUuid?: string
}>()
const emit = defineEmits<{ 'update:show': [boolean]; saved: []; deleted: [] }>()

const { run, pending, confirm } = useAction()
const opts = ref<Options | null>(null)
const loadError = ref('')

const form = reactive({
  domain: '',
  geo: 'default',
  ttl: 60,
  poolMode: 'custom_ips' as PoolMode,
  ipsText: '',
  eips: [] as string[],
  probe: '',
  strategy: 'priority_order',
  qty: 1,
  interval: 5,
  name: '',
  description: '',
})

const editing = computed(() => !!props.rule)
const selectedDomain = computed(() => props.domains?.find((d) => d.uuid === form.domain))

watch(
  () => props.show,
  async (open) => {
    if (!open) return
    reset()
    if (!opts.value) {
      try {
        opts.value = await api.options()
        loadError.value = ''
      } catch (e) {
        loadError.value = e instanceof Error ? e.message : String(e)
      }
    }
  },
  { immediate: true },
)

function reset() {
  const r = props.rule
  Object.assign(form, {
    domain: props.domainUuid ?? props.domains?.[0]?.uuid ?? '',
    geo: r?.geo_isp ?? 'default',
    ttl: r?.ttl ?? 60,
    poolMode: r?.pool_mode ?? 'custom_ips',
    ipsText: (r?.pool ?? []).join('\n'),
    eips: [...(r?.eip_uuids ?? [])],
    probe: r?.edge_probe_templates[0] ?? '',
    strategy: r?.election_strategy || 'priority_order',
    qty: r?.ip_quantity ?? 1,
    interval: r?.trigger_interval ?? 5,
    name: r?.name ?? '',
    description: r?.description ?? '',
  })
}

const ips = computed(() =>
  form.ipsText.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean),
)

const geoOptions = computed(() =>
  opts.value ? geoSelectOptions(opts.value, selectedDomain.value?.provider_type) : [],
)
const domainOptions = computed(() =>
  (props.domains ?? []).map((d) => ({
    value: d.uuid,
    label: `${d.domain}${d.supports_geo_split ? '' : '（不支持境内/境外分流）'}`,
  })),
)
const templateOptions = computed(() => [
  { value: '', label: '不关联地址监控' },
  ...(opts.value?.probe_templates ?? []).map((t) => ({
    value: t.uuid,
    label: t.enabled === false ? `${t.name}（已停用）` : t.name,
  })),
])
const strategyHelp = computed(
  () => opts.value?.strategies.find((s) => s.value === form.strategy)?.help ?? '',
)
const allEipsBlocked = computed(() => !!opts.value?.no_all_eips_strategies.includes(form.strategy))
const noEips = computed(() => !opts.value?.eips.length)

// AxisNow 的限制：「顺序」策略不能用「所有 EIP」
watch(allEipsBlocked, (blocked) => {
  if (blocked && form.poolMode === 'all_eips') form.poolMode = 'custom_ips'
})

function payload(): Record<string, unknown> {
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    geo_isp: form.geo,
    pool_mode: form.poolMode,
    ips: ips.value,
    eip_uuids: form.eips,
    election_strategy: form.strategy,
    ip_quantity: form.qty,
    trigger_interval: form.interval,
    edge_probe_template_uuid: form.probe,
    ttl: form.ttl,
  }
}

async function submit() {
  const done = editing.value
    ? await run('save', () => api.rules.update(props.rule!.uuid, payload()), '规则已更新')
    : await run(
        'save',
        () => api.rules.create({ ...payload(), dns_domain_uuid: form.domain }),
        '规则已创建',
      )
  if (done !== undefined) {
    invalidate('rules', 'domains', 'dashboard', 'rule:')
    emit('update:show', false)
    emit('saved')
  }
}

async function remove() {
  const ok = await confirm({
    title: '删除路由规则',
    content: '删除后该规则会从 AxisNow 移除，对应线路的 DNS 解析随之失效。确认删除？',
    positiveText: '删除',
    danger: true,
  })
  if (!ok) return
  const done = await run('delete', () => api.rules.remove(props.rule!.uuid), '规则已删除')
  if (done !== undefined) {
    invalidate('rules', 'domains', 'dashboard', 'rule:')
    emit('update:show', false)
    emit('deleted')
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="editing ? '编辑路由规则' : '新建路由规则'"
    style="width: 720px; max-width: calc(100vw - 32px)"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <NAlert v-if="loadError" type="error" :show-icon="false">{{ loadError }}</NAlert>
    <NSpin v-else-if="!opts" size="small" class="loading" />
    <NForm v-else label-placement="top" :show-feedback="false" class="form">
      <NFormItem v-if="!editing" label="所属调度域">
        <NSelect v-model:value="form.domain" :options="domainOptions" />
      </NFormItem>
      <p v-else class="muted small editing-target">
        <span class="mono">{{ rule?.domain }}</span> · 记录类型 {{ rule?.record_type }}
      </p>

      <div class="grid-2">
        <NFormItem label="线路">
          <NSelect
            v-model:value="form.geo"
            :options="geoOptions"
            :render-label="renderGeoLabel"
            filterable
          />
        </NFormItem>
        <NFormItem label="TTL（秒）">
          <NInputNumber v-model:value="form.ttl" :min="1" :max="86400" :step="60" style="width: 100%" />
        </NFormItem>
      </div>

      <h4>地址池</h4>
      <NFormItem :show-label="false">
        <NRadioGroup v-model:value="form.poolMode">
          <NRadioButton value="custom_ips">自定义 IP</NRadioButton>
          <NRadioButton value="custom_eips" :disabled="noEips">指定 EIP</NRadioButton>
          <NRadioButton value="all_eips" :disabled="allEipsBlocked || noEips">所有 EIP</NRadioButton>
        </NRadioGroup>
      </NFormItem>

      <NFormItem v-if="form.poolMode === 'custom_ips'" :show-label="false">
        <div class="stack-sm">
          <NInput
            v-model:value="form.ipsText"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            placeholder="每行一个 IP，排在前面的优先级更高"
            class="mono"
          />
          <span class="muted small">
            已填写 {{ ips.length }} 个地址。填自己的服务器 IP 即可，自动去重、校验格式，最多 50 个。
          </span>
        </div>
      </NFormItem>
      <NFormItem v-else-if="form.poolMode === 'custom_eips'" :show-label="false">
        <NCheckboxGroup v-model:value="form.eips">
          <div class="eips">
            <NCheckbox v-for="e in opts.eips" :key="e.uuid" :value="e.uuid">
              <IpBadge :item="e" compact :show-status="false" />
            </NCheckbox>
          </div>
        </NCheckboxGroup>
      </NFormItem>
      <NAlert v-else type="info" :show-icon="false">
        使用账号下全部可用 EIP（当前 {{ opts.eips.length }} 个），AxisNow 会自动同步增减。
      </NAlert>

      <NFormItem label="地址监控">
        <NSelect v-model:value="form.probe" :options="templateOptions" />
      </NFormItem>

      <h4>选取策略</h4>
      <NFormItem :show-label="false">
        <div class="stack-sm">
          <NRadioGroup v-model:value="form.strategy">
            <NRadioButton v-for="s in opts.strategies" :key="s.value" :value="s.value">
              {{ s.label }}
            </NRadioButton>
          </NRadioGroup>
          <span class="muted small">{{ strategyHelp }}</span>
        </div>
      </NFormItem>
      <div class="grid-2">
        <NFormItem label="返回地址数量">
          <NInputNumber v-model:value="form.qty" :min="1" :max="10" style="width: 100%" />
        </NFormItem>
        <NFormItem v-if="form.strategy === 'quality_optimized'" label="评估周期">
          <NRadioGroup v-model:value="form.interval">
            <NRadioButton v-for="n in opts.trigger_intervals" :key="n" :value="n">
              {{ n }} 分钟
            </NRadioButton>
          </NRadioGroup>
        </NFormItem>
      </div>

      <h4>描述</h4>
      <div class="grid-2">
        <NFormItem label="规则名称">
          <NInput v-model:value="form.name" maxlength="100" placeholder="例如 境内线路" />
        </NFormItem>
        <NFormItem label="备注（可选）">
          <NInput v-model:value="form.description" maxlength="255" />
        </NFormItem>
      </div>
    </NForm>

    <template #footer>
      <div class="row">
        <NButton v-if="editing" type="error" ghost :loading="pending === 'delete'" @click="remove">
          删除规则
        </NButton>
        <span class="spacer" />
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton type="primary" :loading="pending === 'save'" :disabled="!opts" @click="submit">
          {{ editing ? '保存' : '创建' }}
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

h4 {
  margin: 8px 0 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border-soft);
  font-size: 13px;
  font-weight: 600;
}

.editing-target {
  margin: 0 0 14px;
}

.stack-sm {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.eips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
</style>
