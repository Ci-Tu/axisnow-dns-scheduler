<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NDropdown, NInput, NRadioButton, NRadioGroup } from 'naive-ui'
import { MoreHorizontal, Play, RefreshCw, Search } from 'lucide-vue-next'
import { api, type Rule } from '@/api'
import RulesTable from '@/components/rules/RulesTable.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import QueryState from '@/components/ui/QueryState.vue'
import { useAction } from '@/composables/useAction'
import { invalidate, useResource } from '@/composables/useResource'

const router = useRouter()
const res = useResource('rules', (fresh) => api.rules.list({ fresh }), { pollMs: 60_000 })
const { run, pending, confirm, message } = useAction()

const tab = ref<'all' | 'managed' | 'unmanaged' | 'faulty'>('all')
const query = ref('')

const rules = computed(() => res.data.value?.rules ?? [])
const counts = computed(() => ({
  all: rules.value.length,
  managed: rules.value.filter((r) => r.managed).length,
  unmanaged: rules.value.filter((r) => !r.managed).length,
  faulty: rules.value.filter((r) => r.probe_summary.unavailable > 0).length,
}))

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rules.value
    .filter((r) =>
      tab.value === 'managed' ? r.managed
        : tab.value === 'unmanaged' ? !r.managed
          : tab.value === 'faulty' ? r.probe_summary.unavailable > 0
            : true)
    .filter((r) =>
      !q || [r.name, r.domain, r.geo_isp_label, r.uuid, ...r.ips.flatMap((i) => [i.ip, i.name, i.note])]
        .join(' ').toLowerCase().includes(q))
})

function refreshAll() {
  invalidate('rules', 'dashboard', 'domains', 'rule:')
}

async function adopt(rule: Rule) {
  if (await run(`adopt:${rule.uuid}`, () => api.rules.adopt(rule.uuid), '已纳入调度') !== undefined) {
    refreshAll()
    router.push(`/rules/${rule.uuid}`)
  }
}

function menu(rule: Rule) {
  return [
    { key: 'toggle', label: rule.enabled ? '暂停自动调度' : '恢复自动调度' },
    { key: 'apply', label: '立即按当前时间下发' },
    { key: 'sync', label: '从 AxisNow 同步 IP 池' },
    { type: 'divider', key: 'd' },
    { key: 'release', label: '移出调度', props: { style: 'color: var(--err)' } },
  ]
}

async function onMenu(key: string, rule: Rule) {
  const id = rule.uuid
  if (key === 'toggle') {
    await run(id, () => api.rules.setEnabled(id, !rule.enabled), rule.enabled ? '已暂停' : '已恢复')
  } else if (key === 'apply') {
    const ok = await confirm({
      title: '立即下发',
      content: '将按当前时间求解目标顺序，并立刻改写该规则在 AxisNow 上的 IP 顺序。',
    })
    if (!ok) return
    await run(id, () => api.rules.apply(id), (r) => `已下发（${r.slot_name ?? '基准顺序'}）`)
  } else if (key === 'sync') {
    await run(id, () => api.rules.sync(id), '已同步最新 IP 池')
  } else if (key === 'release') {
    const ok = await confirm({
      title: '移出调度',
      content: '移出后不再自动下发，该规则在 AxisNow 上的现有顺序保持不变，本地的时间段配置会被删除。',
      positiveText: '移出',
      danger: true,
    })
    if (!ok) return
    await run(id, () => api.rules.release(id), '已移出调度')
  }
  refreshAll()
}

async function tick() {
  const r = await run('tick', () => api.tick())
  if (!r) return
  const s = r.result
  if (s.skipped) message.info(s.skipped)
  else if (s.errors.length) message.warning(`检查 ${s.checked} 条，下发 ${s.applied} 条；${s.errors.join('；')}`)
  else message.success(`检查 ${s.checked} 条规则，下发 ${s.applied} 条`)
  refreshAll()
}
</script>

<template>
  <PageHeader
    title="调度"
    description="把规则纳入调度后，潮汐时间段与拨测故障切换会按设定自动改写 IP 优先级。"
  >
    <template #actions>
      <NInput v-model:value="query" placeholder="搜索线路、域名或 IP" clearable style="width: 220px">
        <template #prefix><Search :size="14" /></template>
      </NInput>
      <NButton :loading="res.refreshing.value" @click="res.refresh(true)">
        <template #icon><RefreshCw :size="14" /></template>
      </NButton>
      <NButton type="primary" :loading="pending === 'tick'" @click="tick">
        <template #icon><Play :size="14" /></template>
        立即调度一轮
      </NButton>
    </template>
  </PageHeader>

  <QueryState
    :loading="res.loading.value"
    :error="res.error.value"
    :has-data="!!res.data.value"
    :rows="8"
    @retry="res.refresh(true)"
  >
    <NCard size="small" content-style="padding: 0">
      <template #header>
        <NRadioGroup v-model:value="tab" size="small">
          <NRadioButton value="all">全部 {{ counts.all }}</NRadioButton>
          <NRadioButton value="managed">已纳入 {{ counts.managed }}</NRadioButton>
          <NRadioButton value="unmanaged">未纳入 {{ counts.unmanaged }}</NRadioButton>
          <NRadioButton v-if="counts.faulty" value="faulty">有故障 {{ counts.faulty }}</NRadioButton>
        </NRadioGroup>
      </template>
      <RulesTable :rules="visible" show-domain :empty-text="query ? '没有匹配的规则' : '没有规则'">
        <template #actions="{ rule }">
          <div class="row actions">
            <template v-if="rule.managed">
              <NButton size="small" @click="router.push(`/rules/${rule.uuid}`)">配置</NButton>
              <NDropdown trigger="click" :options="menu(rule)" @select="(k: string) => onMenu(k, rule)">
                <NButton size="small" quaternary :loading="pending === rule.uuid">
                  <template #icon><MoreHorizontal :size="15" /></template>
                </NButton>
              </NDropdown>
            </template>
            <NButton
              v-else
              size="small"
              type="primary"
              secondary
              :loading="pending === `adopt:${rule.uuid}`"
              @click="adopt(rule)"
            >
              纳入调度
            </NButton>
          </div>
        </template>
      </RulesTable>
    </NCard>
  </QueryState>
</template>

<style scoped>
.actions {
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 4px;
}
</style>
