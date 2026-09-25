<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NInput, NSwitch, NTag } from 'naive-ui'
import { ArrowLeft, Pencil, RefreshCw, Send } from 'lucide-vue-next'
import { api, type Rule } from '@/api'
import RuleFormModal from '@/components/rules/RuleFormModal.vue'
import TideEditor from '@/components/rules/TideEditor.vue'
import Callout from '@/components/ui/Callout.vue'
import IpBadge from '@/components/ui/IpBadge.vue'
import IpNameEditor from '@/components/ui/IpNameEditor.vue'
import LineTag from '@/components/ui/LineTag.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import QueryState from '@/components/ui/QueryState.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import { useAction } from '@/composables/useAction'
import { invalidate, useResource } from '@/composables/useResource'
import { fmtRelative, fmtTime } from '@/utils/format'

const props = defineProps<{ uuid: string }>()
const router = useRouter()
const { run, pending, confirm } = useAction()

const res = useResource<Rule>(`rule:${props.uuid}`, (fresh) =>
  api.rules.get(props.uuid, { fresh }).then((r) => r.rule),
)
const rule = computed(() => res.data.value)
const tide = computed(() => rule.value?.features.find((f) => f.id === 'tide'))
const failover = computed(() => rule.value?.features.find((f) => f.id === 'probe_failover'))
const showEdit = ref(false)

// 规则内 IP 备注的本地草稿
const notes = reactive<Record<string, string>>({})
watch(rule, (r) => r?.ips.forEach((i) => (notes[i.ip] = i.note)), { immediate: true })

function changed() {
  invalidate(`rule:${props.uuid}`, 'rules', 'dashboard', 'domains')
}

async function adopt() {
  if (await run('adopt', () => api.rules.adopt(props.uuid), '已纳入调度') !== undefined) changed()
}

async function apply() {
  const ok = await confirm({
    title: '立即下发',
    content: '将按当前时间求解目标顺序，并立刻改写该规则在 AxisNow 上的 IP 顺序。',
  })
  if (!ok) return
  const r = await run('apply', () => api.rules.apply(props.uuid), (x) => `已下发（${x.slot_name ?? '基准顺序'}）`)
  if (r) changed()
}

async function sync() {
  if (await run('sync', () => api.rules.sync(props.uuid), '已从 AxisNow 同步 IP 池') !== undefined) changed()
}

async function toggleFeature(fid: string, enabled: boolean) {
  const done = await run(`f:${fid}`, () => api.rules.setFeatureEnabled(props.uuid, fid, enabled),
    enabled ? '功能已启用' : '功能已停用')
  if (done !== undefined) changed()
}

async function toggleRule(enabled: boolean) {
  const done = await run('enabled', () => api.rules.setEnabled(props.uuid, enabled),
    enabled ? '已恢复自动调度' : '已暂停自动调度')
  if (done !== undefined) changed()
}

async function saveNote(ip: string) {
  const done = await run(`note:${ip}`, () => api.rules.setNote(props.uuid, ip, notes[ip] ?? ''), '备注已保存')
  if (done !== undefined) changed()
}

function featureStatus(f: Rule['features'][number]): { text: string; type: 'success' | 'default' | 'warning' | 'error' } {
  if (!f.enabled) return { text: '已停用', type: 'default' }
  if (!f.applicable) return { text: '不适用', type: 'warning' }
  const s = f.summary as Record<string, unknown>
  if (f.id === 'tide') {
    return s.active_slot_name ? { text: `命中 ${s.active_slot_name}`, type: 'success' } : { text: '使用基准顺序', type: 'default' }
  }
  if (f.id === 'probe_failover') {
    const n = (s.demoted as string[] | undefined)?.length ?? 0
    return n ? { text: `已降级 ${n} 个`, type: 'error' } : { text: '全部正常', type: 'success' }
  }
  return { text: '生效中', type: 'success' }
}
</script>

<template>
  <QueryState :loading="res.loading.value" :error="res.error.value" :has-data="!!rule" :rows="10"
    @retry="res.refresh(true)">
    <template v-if="rule">
      <PageHeader :title="rule.domain || rule.name">
        <template #before-title>
          <RouterLink to="/scheduling" class="back small">
            <ArrowLeft :size="13" /> 调度
          </RouterLink>
        </template>
        <template #description>
          <span class="row">
            <LineTag :label="rule.geo_isp_label" :region="rule.geo_isp_region" />
            <span>·</span>
            <span>{{ rule.name || '未命名' }}</span>
            <span>·</span>
            <span>{{ rule.election_label }}，返回 {{ rule.ip_quantity ?? '—' }} 个</span>
            <span>·</span>
            <span>TTL {{ rule.ttl ?? '—' }}s</span>
          </span>
        </template>
        <template #actions>
          <NButton @click="showEdit = true">
            <template #icon><Pencil :size="14" /></template>
            编辑规则
          </NButton>
          <NButton :loading="pending === 'sync'" @click="sync">
            <template #icon><RefreshCw :size="14" /></template>
            同步 IP 池
          </NButton>
          <NButton v-if="rule.managed" type="primary" :loading="pending === 'apply'" @click="apply">
            <template #icon><Send :size="14" /></template>
            立即下发
          </NButton>
        </template>
      </PageHeader>

      <Callout v-if="!rule.managed" type="info" class="gap">
        这条规则还没有纳入调度，下面的功能配置不会自动生效。
        <template #action>
          <NButton type="primary" size="small" :loading="pending === 'adopt'" @click="adopt">纳入调度</NButton>
        </template>
      </Callout>

      <div class="layout">
        <div class="stack">
          <TideEditor v-if="tide && rule.managed" :rule="rule" :feature="tide" @changed="changed" />

          <NCard title="地址池" size="small">
            <template #header-extra>
              <span class="muted small">名称全局共用；备注只属于这条规则</span>
            </template>
            <table class="ips">
              <thead>
                <tr><th>地址</th><th>拨测</th><th>名称</th><th>规则内备注</th></tr>
              </thead>
              <tbody>
                <tr v-for="(ip, i) in rule.ips" :key="ip.ip">
                  <td><IpBadge :item="ip" :rank="i + 1" :show-status="false" :show-label="false" show-org /></td>
                  <td>
                    <StatusDot :status="ip.probe?.status" label />
                  </td>
                  <td>
                    <span class="row nowrap">
                      <span :class="{ muted: !ip.name }">{{ ip.name || '—' }}</span>
                      <IpNameEditor :ip="ip.ip" :name="ip.name" @saved="changed" />
                    </span>
                  </td>
                  <td>
                    <NInput
                      v-model:value="notes[ip.ip]"
                      size="small"
                      maxlength="32"
                      placeholder="例如 家宽 / 备用"
                      :disabled="pending === `note:${ip.ip}`"
                      @blur="notes[ip.ip] !== ip.note && saveNote(ip.ip)"
                      @keyup.enter="saveNote(ip.ip)"
                    />
                  </td>
                </tr>
                <tr v-if="!rule.ips.length">
                  <td colspan="4" class="muted">该规则的地址池里没有 IP 类型的地址组</td>
                </tr>
              </tbody>
            </table>
          </NCard>
        </div>

        <div class="stack">
          <NCard v-if="rule.managed" title="功能模块" size="small">
            <div class="features">
              <div class="feature">
                <div class="row">
                  <span class="f-name">自动调度</span>
                  <span class="spacer" />
                  <NSwitch :value="rule.enabled" :loading="pending === 'enabled'" @update:value="toggleRule" />
                </div>
                <p class="muted small">关闭后保留所有配置，但不再自动下发。</p>
              </div>
              <div v-for="f in rule.features" :key="f.id" class="feature">
                <div class="row">
                  <span class="f-name">{{ f.name }}</span>
                  <NTag size="small" :type="featureStatus(f).type" :bordered="false">{{ featureStatus(f).text }}</NTag>
                  <span class="spacer" />
                  <NSwitch :value="f.enabled" :loading="pending === `f:${f.id}`" @update:value="(v: boolean) => toggleFeature(f.id, v)" />
                </div>
                <p class="muted small">{{ f.applicable || !f.enabled ? f.description : f.reason }}</p>
              </div>
            </div>
          </NCard>

          <NCard v-if="failover?.applicable && rule.managed" title="拨测故障切换" size="small">
            <dl class="kv">
              <dt>可用</dt><dd class="num">{{ failover.summary.healthy }}</dd>
              <dt>不可用</dt><dd class="num">{{ failover.summary.unhealthy }}</dd>
              <dt>无数据</dt><dd class="num">{{ failover.summary.unknown }}</dd>
            </dl>
          </NCard>

          <NCard title="状态" size="small">
            <dl class="kv">
              <dt>上次下发</dt>
              <dd>
                <template v-if="rule.last_applied">
                  {{ fmtRelative(rule.last_applied.at) }}（{{ rule.last_applied.slot_name || '基准顺序' }}）
                </template>
                <span v-else class="muted">本次运行尚未下发</span>
              </dd>
              <dt>目标顺序</dt>
              <dd>
                <span v-if="rule.desired_order" class="mono small">{{ rule.desired_order.join(' → ') }}</span>
                <span v-else class="muted">—</span>
              </dd>
              <dt>AxisNow 更新</dt><dd>{{ fmtTime(rule.updated_at) }}</dd>
              <dt>拨测模板</dt><dd>{{ rule.edge_probe_templates.length ? '已关联' : '未关联' }}</dd>
              <dt>规则 ID</dt><dd class="mono small">{{ rule.uuid }}</dd>
            </dl>
          </NCard>
        </div>
      </div>

      <RuleFormModal
        v-model:show="showEdit"
        :rule="rule"
        @saved="changed"
        @deleted="router.replace('/scheduling')"
      />
    </template>
  </QueryState>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-3);
  margin-bottom: 6px;
}

.gap {
  margin-bottom: 16px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}

.ips {
  width: 100%;
  border-collapse: collapse;
}

.ips th {
  text-align: left;
  font-weight: 500;
  font-size: 12.5px;
  color: var(--text-3);
  padding: 4px 8px 8px;
  border-bottom: 1px solid var(--border);
}

.ips td {
  padding: 8px;
  border-bottom: 1px solid var(--border-soft);
}

.ips tr:last-child td {
  border-bottom: none;
}

.nowrap {
  flex-wrap: nowrap;
}

.features {
  display: flex;
  flex-direction: column;
}

.feature {
  padding: 10px 0;
  border-top: 1px solid var(--border-soft);
}

.feature:first-child {
  border-top: none;
  padding-top: 0;
}

.feature p {
  margin: 4px 0 0;
}

.f-name {
  font-weight: 500;
}

@media (max-width: 1100px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
