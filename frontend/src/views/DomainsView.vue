<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NCard, NDropdown, NEmpty, NInput, NTag } from 'naive-ui'
import { Cloud, MoreHorizontal, Plus, RefreshCw, Search } from 'lucide-vue-next'
import { api, type Domain, type Rule } from '@/api'
import CloudflareLinkModal from '@/components/rules/CloudflareLinkModal.vue'
import DomainCreateModal from '@/components/rules/DomainCreateModal.vue'
import RuleFormModal from '@/components/rules/RuleFormModal.vue'
import RulesTable from '@/components/rules/RulesTable.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import QueryState from '@/components/ui/QueryState.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import { useAction } from '@/composables/useAction'
import { invalidate, useResource } from '@/composables/useResource'

const res = useResource('domains', (fresh) => api.domains.list({ fresh }).then((r) => r.domains))
const { run, confirm } = useAction()

const query = ref('')
const showDomainModal = ref(false)
const ruleModal = ref<{ show: boolean; rule: Rule | null; domainUuid?: string }>({ show: false, rule: null })
const cfModal = ref({ show: false, target: '' })

const domains = computed(() => res.data.value ?? [])
const activeDomains = computed(() => domains.value.filter((d) => d.status === 'active'))
const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return domains.value
  return domains.value.filter((d) =>
    [d.domain, d.provider_type, d.zone, ...d.rules.flatMap((r) => [r.name, r.geo_isp_label, ...r.pool])]
      .join(' ')
      .toLowerCase()
      .includes(q),
  )
})

function newRule(domainUuid?: string) {
  ruleModal.value = { show: true, rule: null, domainUuid }
}

function domainMenu(d: Domain) {
  return [
    { key: 'cf', label: '接入 Cloudflare…' },
    { key: 'rule', label: '新建规则…' },
    { type: 'divider', key: 'd1' },
    { key: 'delete', label: '删除调度域', props: { style: 'color: var(--err)' } },
  ].map((o) => ({ ...o, domain: d }))
}

async function onDomainAction(key: string, d: Domain) {
  if (key === 'cf') cfModal.value = { show: true, target: d.domain }
  if (key === 'rule') newRule(d.uuid)
  if (key === 'delete') {
    const ok = await confirm({
      title: `删除调度域 ${d.domain}`,
      content: `该域下的 ${d.rules.length} 条规则会一并删除，解析立即失效。此操作无法撤销。`,
      positiveText: '删除',
      danger: true,
    })
    if (!ok) return
    const done = await run('delete', () => api.domains.remove(d.uuid), '调度域已删除')
    if (done !== undefined) invalidate('domains', 'rules', 'dashboard')
  }
}

function onDomainCreated(domain: string) {
  cfModal.value = { show: true, target: domain }
}
</script>

<template>
  <PageHeader title="域名与规则" description="调度域及其下的路由规则：线路、地址池与选取策略。">
    <template #actions>
      <NInput v-model:value="query" placeholder="搜索域名、线路或 IP" clearable style="width: 220px">
        <template #prefix><Search :size="14" /></template>
      </NInput>
      <NButton :loading="res.refreshing.value" @click="res.refresh(true)">
        <template #icon><RefreshCw :size="14" /></template>
      </NButton>
      <NButton :disabled="!activeDomains.length" @click="newRule()">
        <template #icon><Plus :size="14" /></template>
        新建规则
      </NButton>
      <NButton type="primary" @click="showDomainModal = true">
        <template #icon><Plus :size="14" /></template>
        新建调度域
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
    <div class="stack">
      <NEmpty v-if="!visible.length" :description="domains.length ? '没有匹配的域名' : '账号下还没有调度域'" />
      <NCard v-for="d in visible" :key="d.uuid" size="small" class="domain" content-style="padding: 0">
        <template #header>
          <div class="row domain-head">
            <span class="mono domain-name">{{ d.domain }}</span>
            <NTag size="small" :bordered="false">{{ d.record_type }}</NTag>
            <NTag size="small" :bordered="false" :type="d.provider_source === 'platform' ? 'info' : 'default'">
              {{ d.provider_source === 'platform' ? 'AxisNow 托管' : d.provider_type || '自托管' }}
            </NTag>
            <NTag v-if="!d.supports_geo_split" size="small" type="warning" :bordered="false">
              不支持分线路
            </NTag>
          </div>
        </template>
        <template #header-extra>
          <div class="row">
            <StatusDot :status="d.status === 'active' ? 'available' : 'unknown'" />
            <span class="small sub">{{ d.status }}</span>
            <NButton size="small" quaternary @click="cfModal = { show: true, target: d.domain }">
              <template #icon><Cloud :size="14" /></template>
              接入 Cloudflare
            </NButton>
            <NDropdown
              trigger="click"
              :options="domainMenu(d)"
              @select="(k: string) => onDomainAction(k, d)"
            >
              <NButton size="small" quaternary>
                <template #icon><MoreHorizontal :size="15" /></template>
              </NButton>
            </NDropdown>
          </div>
        </template>

        <RulesTable :rules="d.rules" empty-text="该域名下还没有路由规则">
          <template #actions="{ rule }">
            <NButton size="small" @click="ruleModal = { show: true, rule }">编辑</NButton>
          </template>
        </RulesTable>
      </NCard>
    </div>
  </QueryState>

  <DomainCreateModal v-model:show="showDomainModal" @created="onDomainCreated" />
  <RuleFormModal
    v-model:show="ruleModal.show"
    :rule="ruleModal.rule"
    :domains="activeDomains"
    :domain-uuid="ruleModal.domainUuid"
  />
  <CloudflareLinkModal v-model:show="cfModal.show" :target="cfModal.target" />
</template>

<style scoped>
.domain-head {
  gap: 8px;
}

.domain-name {
  font-size: 14px;
  font-weight: 500;
}
</style>
