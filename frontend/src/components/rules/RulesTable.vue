<script setup lang="ts">
import { NTag } from 'naive-ui'
import type { Rule } from '@/api'
import IpBadge from '@/components/ui/IpBadge.vue'
import LineTag from '@/components/ui/LineTag.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import { fmtRelative } from '@/utils/format'

defineProps<{ rules: Rule[]; showDomain?: boolean; emptyText?: string }>()

const GROUP_LABEL: Record<string, string> = { ip: 'IP', eip: 'EIP', eip_tag: 'EIP 标签', domain: '域名' }

function schedule(rule: Rule): { text: string; type: 'success' | 'default' | 'warning' | 'error' }[] {
  if (!rule.managed) return []
  const out: { text: string; type: 'success' | 'default' | 'warning' | 'error' }[] = []
  for (const f of rule.features) {
    if (!f.enabled) continue
    const s = f.summary as Record<string, unknown>
    if (f.id === 'tide') {
      if (!f.applicable) out.push({ text: '潮汐不适用', type: 'warning' })
      else if (s.active_slot_name) out.push({ text: `潮汐 · ${s.active_slot_name}`, type: 'success' })
      else out.push({ text: `潮汐 · ${Number(s.slot_count ?? 0)} 个时段`, type: 'default' })
    } else if (f.id === 'probe_failover' && f.applicable) {
      const demoted = (s.demoted as string[] | undefined)?.length ?? 0
      out.push(demoted ? { text: `故障切换 · 已降级 ${demoted}`, type: 'error' }
        : { text: '故障切换', type: 'default' })
    }
  }
  return out
}
</script>

<template>
  <div class="table-wrap">
    <table class="rules">
      <thead>
        <tr>
          <th class="c-line">线路</th>
          <th>地址池（按优先级）</th>
          <th class="c-strategy">选取策略</th>
          <th class="c-probe">拨测</th>
          <th class="c-sched">调度</th>
          <th class="c-actions" />
        </tr>
      </thead>
      <tbody>
        <tr v-if="!rules.length">
          <td colspan="6" class="empty muted">{{ emptyText ?? '没有路由规则' }}</td>
        </tr>
        <tr v-for="r in rules" :key="r.uuid">
          <td class="c-line">
            <LineTag :label="r.geo_isp_label" :region="r.geo_isp_region" />
            <div class="muted small ellipsis">{{ r.name || '未命名' }}</div>
            <div v-if="showDomain" class="muted small mono ellipsis">{{ r.domain }}</div>
          </td>
          <td>
            <div class="pool">
              <IpBadge
                v-for="(ip, i) in r.ips"
                :key="ip.ip"
                :item="ip"
                :rank="r.election_strategy === 'priority_order' ? i + 1 : null"
                compact
              />
              <NTag
                v-for="g in r.group_types.filter((t) => t !== 'ip')"
                :key="g"
                size="small"
                :bordered="false"
              >
                {{ GROUP_LABEL[g] ?? g }}
              </NTag>
              <span v-if="!r.ips.length && !r.group_types.length" class="muted small">空</span>
            </div>
            <div class="muted small">
              更新于 {{ fmtRelative(r.updated_at) }}
              <template v-if="r.last_applied"> · 本机下发于 {{ fmtRelative(r.last_applied.at) }}</template>
            </div>
          </td>
          <td class="c-strategy">
            <div>{{ r.election_label }}</div>
            <div class="muted small">
              {{ r.election_strategy === 'quality_optimized' ? `每 ${r.trigger_interval ?? 5} 分钟评估` : `返回 ${r.ip_quantity ?? '—'} 个` }}
            </div>
          </td>
          <td class="c-probe">
            <template v-if="r.probe_summary.known">
              <StatusDot
                :status="r.probe_summary.unavailable ? 'unavailable' : 'available'"
                label
              />
              <div class="muted small num">
                {{ r.probe_summary.available }}/{{ r.probe_summary.total }} 可用
              </div>
            </template>
            <span v-else class="muted small">
              {{ r.edge_probe_templates.length ? '暂无数据' : '未关联' }}
            </span>
          </td>
          <td class="c-sched">
            <template v-if="r.managed">
              <div class="tags">
                <NTag v-if="!r.enabled" size="small" :bordered="false">已暂停</NTag>
                <NTag v-for="t in schedule(r)" :key="t.text" size="small" :type="t.type" :bordered="false">
                  {{ t.text }}
                </NTag>
              </div>
            </template>
            <span v-else class="muted small">未纳入</span>
          </td>
          <td class="c-actions">
            <slot name="actions" :rule="r" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.table-wrap {
  overflow-x: auto;
}

.rules {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 860px;
}

th {
  text-align: left;
  font-weight: 500;
  font-size: 12.5px;
  color: var(--text-3);
  padding: 8px 12px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

td {
  padding: 12px;
  border-bottom: 1px solid var(--border-soft);
  vertical-align: top;
}

tbody tr:last-child td {
  border-bottom: none;
}

tbody tr:hover td {
  background: color-mix(in srgb, var(--surface-2) 60%, transparent);
}

.c-line {
  width: 170px;
}

.c-strategy {
  width: 120px;
}

.c-probe {
  width: 110px;
}

.c-sched {
  width: 180px;
}

.c-actions {
  width: 120px;
  white-space: nowrap;
  text-align: right;
}

.pool {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.empty {
  text-align: center;
  padding: 28px;
}

.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
