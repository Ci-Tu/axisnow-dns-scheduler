<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCard, NEmpty, NTag } from 'naive-ui'
import { RefreshCw } from 'lucide-vue-next'
import { api, type Dashboard, type ProbeHistory } from '@/api'
import IpNameEditor from '@/components/ui/IpNameEditor.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import QueryState from '@/components/ui/QueryState.vue'
import RegionFlag from '@/components/ui/RegionFlag.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import UptimeBar from '@/components/ui/UptimeBar.vue'
import { useResource } from '@/composables/useResource'
import { countryName } from '@/utils/countries'
import { fmtPercent, fmtRelative, fmtTime } from '@/utils/format'

const board = useResource<Dashboard>('dashboard', (fresh) => api.dashboard({ fresh }), {
  pollMs: 60_000,
})
const hist = useResource<ProbeHistory>('probe:history', () => api.probe.history(), {
  pollMs: 60_000,
})

const d = computed(() => board.data.value)
const nodes = computed(() => d.value?.nodes ?? [])
const healthy = computed(() => nodes.value.filter((n) => n.probe?.status === 'available').length)
const down = computed(() => nodes.value.filter((n) => n.probe?.status === 'unavailable').length)

const schedulerText = computed(() => {
  const s = d.value?.scheduler
  if (!s) return ''
  if (!s.enabled) return '自动调度已暂停'
  if (!s.running) return '调度线程未运行（DISABLE_SCHEDULER=1 或由其他进程负责）'
  if (s.last_error) return `调度出现问题：${s.last_error}`
  return s.last_tick ? `自动调度运行中 · 上次轮询 ${fmtRelative(s.last_tick)}` : '自动调度运行中'
})

function refresh() {
  void board.refresh(true)
  void hist.refresh()
}
</script>

<template>
  <PageHeader title="仪表盘">
    <template #description>
      <span class="row">
        <StatusDot
          :status="!d?.scheduler.enabled || !d?.scheduler.running ? null : d?.scheduler.last_error ? 'unavailable' : 'available'"
        />
        <span>{{ schedulerText || '读取中…' }}</span>
      </span>
    </template>
    <template #actions>
      <NButton :loading="board.refreshing.value" @click="refresh">
        <template #icon><RefreshCw :size="14" /></template>
        刷新
      </NButton>
    </template>
  </PageHeader>

  <QueryState
    :loading="board.loading.value"
    :error="board.error.value"
    :has-data="!!d"
    :rows="8"
    @retry="refresh"
  >
    <template v-if="d">
      <section class="metrics">
        <RouterLink to="/domains" class="metric">
          <span class="label">调度域</span>
          <span class="value num">{{ d.counts.domains }}</span>
        </RouterLink>
        <RouterLink to="/scheduling" class="metric">
          <span class="label">路由规则</span>
          <span class="value num">{{ d.counts.rules }}</span>
          <span class="hint">{{ d.counts.managed_rules }} 条已纳入调度</span>
        </RouterLink>
        <RouterLink to="/probe" class="metric">
          <span class="label">节点</span>
          <span class="value num">
            {{ healthy }}<span class="of">/{{ nodes.length }}</span>
          </span>
          <span class="hint" :class="{ bad: down }">{{ down ? `${down} 个不可用` : '全部可用' }}</span>
        </RouterLink>
        <RouterLink to="/probe" class="metric">
          <span class="label">拨测任务</span>
          <span class="value num">{{ d.counts.probe_tasks }}</span>
          <span class="hint">{{ d.counts.probe_templates }} 个模板</span>
        </RouterLink>
        <RouterLink to="/cloudflare" class="metric">
          <span class="label">Cloudflare</span>
          <span class="value text">{{ d.cloudflare.configured ? '已接入' : '未接入' }}</span>
        </RouterLink>
      </section>

      <div class="main-grid">
        <NCard title="节点健康" size="small" class="nodes-card">
          <template #header-extra>
            <span class="muted small">近 24 小时 · 每分钟采样</span>
          </template>
          <NEmpty v-if="!nodes.length" description="规则的地址池里还没有 IP" />
          <table v-else class="nodes">
            <tbody>
              <tr v-for="n in nodes" :key="n.ip">
                <td class="who">
                  <div class="row nowrap">
                    <RegionFlag :code="n.geo.country" :size="13" />
                    <span class="node-name">{{ n.name || n.ip }}</span>
                    <IpNameEditor :ip="n.ip" :name="n.name" />
                  </div>
                  <div class="muted small ellipsis">
                    <span v-if="n.name" class="mono">{{ n.ip }} · </span>
                    <span v-if="n.geo.country">{{ countryName(n.geo.country) }}</span>
                    <span v-if="n.geo.org"> · {{ n.geo.org }}</span>
                    <span v-if="n.geo.private">内网 / 保留地址</span>
                  </div>
                </td>
                <td class="c-lines">
                  <NTag v-for="l in n.lines" :key="l" size="small" :bordered="false">{{ l }}</NTag>
                </td>
                <td class="c-uptime">
                  <UptimeBar :samples="hist.data.value?.samples[n.ip] ?? []" />
                  <div class="muted small num">
                    {{ fmtPercent(n.uptime) }} · {{ n.samples }} 次采样
                  </div>
                </td>
                <td class="c-state"><StatusDot :status="n.probe?.status" label /></td>
              </tr>
            </tbody>
          </table>
        </NCard>

        <NCard title="最近调度" size="small">
          <template #header-extra>
            <RouterLink to="/settings?tab=history" class="small">全部</RouterLink>
          </template>
          <NEmpty v-if="!d.events.length" description="还没有下发记录" />
          <ol v-else class="timeline">
            <li v-for="(e, i) in d.events" :key="i" :class="{ bad: !e.ok }">
              <div class="row">
                <span class="event-title">{{ e.slot || (e.ok ? '基准顺序' : '下发失败') }}</span>
                <span class="spacer" />
                <span class="muted small" :title="fmtTime(e.at, true)">{{ fmtRelative(e.at) }}</span>
              </div>
              <div class="muted small ellipsis">
                {{ e.line }} · {{ e.domain }}<template v-if="!e.ok"> · {{ e.message }}</template>
              </div>
            </li>
          </ol>
        </NCard>
      </div>

      <NCard title="调度域" size="small">
        <template #header-extra>
          <RouterLink to="/domains" class="small">管理</RouterLink>
        </template>
        <NEmpty v-if="!d.domains.length" description="还没有调度域" />
        <table v-else class="domains">
          <thead>
            <tr>
              <th>域名</th>
              <th>服务商</th>
              <th>记录类型</th>
              <th class="r">规则</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="x in d.domains" :key="x.uuid">
              <td class="mono">{{ x.domain }}</td>
              <td class="sub">{{ x.provider_type || '—' }}</td>
              <td>{{ x.record_type }}</td>
              <td class="r num">{{ x.rules }}</td>
              <td>
                <span class="row">
                  <StatusDot :status="x.status === 'active' ? 'available' : 'unknown'" />
                  <span class="small sub">{{ x.status }}</span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </NCard>
    </template>
  </QueryState>
</template>

<style scoped>
.metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 16px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px 18px;
  color: inherit;
  text-decoration: none;
  border-left: 1px solid var(--border-soft);
  transition: background-color 0.12s;
}

.metric:first-child {
  border-left: none;
}

.metric:hover {
  background: var(--surface-2);
  text-decoration: none;
}

.metric .label {
  font-size: 12.5px;
  color: var(--text-3);
}

.metric .value {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
}

.metric .value.text {
  font-size: 17px;
  line-height: 36px;
}

.metric .of {
  font-size: 15px;
  color: var(--text-3);
  font-weight: 500;
}

.metric .hint {
  font-size: 12px;
  color: var(--text-3);
}

.metric .hint.bad {
  color: var(--err);
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

table {
  width: 100%;
  border-collapse: collapse;
}

.nodes td {
  padding: 10px 8px;
  border-top: 1px solid var(--border-soft);
  vertical-align: middle;
}

.nodes tr:first-child td {
  border-top: none;
}

.who {
  max-width: 280px;
}

.node-name {
  font-weight: 500;
}

.c-lines {
  width: 1%;
  white-space: nowrap;
}

.c-lines :deep(.n-tag) {
  margin-right: 4px;
}

.c-uptime {
  width: 1%;
  white-space: nowrap;
}

.c-state {
  width: 1%;
  white-space: nowrap;
  text-align: right;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline li {
  position: relative;
  padding: 8px 0 8px 16px;
  border-left: 1px solid var(--border);
}

.timeline li::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 14px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
}

.timeline li.bad::before {
  background: var(--err);
}

.event-title {
  font-weight: 500;
}

.domains th {
  text-align: left;
  font-weight: 500;
  color: var(--text-3);
  font-size: 12.5px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.domains td {
  padding: 9px 8px;
  border-bottom: 1px solid var(--border-soft);
}

.domains tr:last-child td {
  border-bottom: none;
}

.r {
  text-align: right;
}

.nowrap {
  flex-wrap: nowrap;
  gap: 6px;
}

.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
