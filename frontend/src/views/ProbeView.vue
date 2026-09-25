<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { Copy, RefreshCw, Trash2 } from 'lucide-vue-next'
import { api, type ProbeHistory, type ProbeOverview } from '@/api'
import Callout from '@/components/ui/Callout.vue'
import IpBadge from '@/components/ui/IpBadge.vue'
import IpNameEditor from '@/components/ui/IpNameEditor.vue'
import LineTag from '@/components/ui/LineTag.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import QueryState from '@/components/ui/QueryState.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import UptimeBar from '@/components/ui/UptimeBar.vue'
import { useAction } from '@/composables/useAction'
import { invalidate, useResource } from '@/composables/useResource'
import { copyText, fmtPercent } from '@/utils/format'

const res = useResource<ProbeOverview>('probe:overview', (fresh) => api.probe.overview({ fresh }), {
  pollMs: 60_000,
})
const hist = useResource<ProbeHistory>('probe:history', () => api.probe.history(), { pollMs: 60_000 })
const { run, pending, confirm, message } = useAction()

const tab = ref('nodes')
const ov = computed(() => res.data.value)
const templateOptions = computed(() =>
  (ov.value?.templates ?? []).map((t) => ({ value: t.uuid, label: t.name })),
)

function changed() {
  invalidate('probe:', 'dashboard', 'rules', 'domains')
}

// ---------- 任务 ----------
const keepTemplate = ref<string | null>(null)

async function cleanup() {
  const ok = await confirm({
    title: '清理重复任务',
    content: '同一个目标 IP 只保留一个拨测任务（优先保留所选模板的），其余任务会从 AxisNow 删除。',
    positiveText: '清理',
    danger: true,
  })
  if (!ok) return
  const r = await run('cleanup', () => api.probe.cleanup(keepTemplate.value ?? ''))
  if (r) {
    message.success(`已删除 ${r.deleted.length} 个任务，保留 ${r.kept} 个`)
    changed()
  }
}

async function deleteTask(uuid: string, name: string) {
  const ok = await confirm({ title: '删除拨测任务', content: `删除「${name}」？`, positiveText: '删除', danger: true })
  if (ok && (await run(`task:${uuid}`, () => api.probe.deleteTask(uuid), '已删除')) !== undefined) changed()
}

// ---------- 统一探针向导 ----------
const wizard = reactive({
  host: '',
  name: '统一探针（自建节点）',
  base: null as string | null,
  scheme: 'http',
  port: 80,
  method: 'HEAD',
  path: '/aegis_node_ping/',
  hostMode: 'custom' as 'custom' | 'follow_target',
  applyTemplate: null as string | null,
  rules: [] as string[],
})

watch(ov, (v) => {
  if (!v) return
  wizard.base ??= v.templates[0]?.uuid ?? null
  wizard.applyTemplate ??= v.templates[0]?.uuid ?? null
  if (!wizard.rules.length) wizard.rules = v.rules.map((r) => r.uuid)
}, { immediate: true })

const hostForConf = computed(() => wizard.host.trim() || 'probe.example.com')
const responderConf = computed(() => `# AxisNow 拨测应答端点：放进 OpenResty / Nginx 的 conf.d
server {
    listen ${wizard.port};
    server_name ${hostForConf.value};   # 所有节点保持一致
    access_log off;

    location = ${wizard.path} {
        default_type text/plain;
        add_header Cache-Control "no-store" always;
        return 200 "ok\\n";
    }
    location / { return 404; }
}`)

async function copyConf() {
  if (await copyText(responderConf.value)) message.success('已复制')
  else message.error('复制失败，请手动选中复制')
}

async function createTemplate() {
  const r = await run('tpl', () => api.probe.createTemplate({
    name: wizard.name,
    base_template_uuid: wizard.base,
    scheme: wizard.scheme,
    port: wizard.port,
    method: wizard.method,
    path: wizard.path,
    host_mode: wizard.hostMode,
    host_value: wizard.host.trim(),
  }), (x) => `模板「${x.template.name}」已创建`)
  if (r) {
    wizard.applyTemplate = r.template.uuid
    changed()
  }
}

async function applyTemplate() {
  if (!wizard.applyTemplate) return
  const r = await run('apply', () => api.probe.apply(wizard.applyTemplate!, wizard.rules))
  if (!r) return
  if (r.failed) message.warning(`成功 ${r.applied} 条，失败 ${r.failed} 条`)
  else message.success(`已应用到 ${r.applied} 条规则`)
  changed()
}

function healthText(h: ProbeOverview['templates'][number]['health']) {
  if (!h.known) return { text: '暂无数据', type: 'default' as const }
  if (!h.available) return { text: `全部不可用（${h.unavailable}）`, type: 'error' as const }
  if (h.unavailable) return { text: `${h.available} 可用 · ${h.unavailable} 不可用`, type: 'warning' as const }
  return { text: `全部可用（${h.available}）`, type: 'success' as const }
}
</script>

<template>
  <PageHeader title="拨测" description="AxisNow 边缘探针对各节点的实测可用性，以及拨测模板与任务管理。">
    <template #actions>
      <NButton :loading="res.refreshing.value" @click="res.refresh(true); hist.refresh()">
        <template #icon><RefreshCw :size="14" /></template>
        刷新
      </NButton>
    </template>
  </PageHeader>

  <QueryState :loading="res.loading.value" :error="res.error.value" :has-data="!!ov" :rows="8"
    @retry="res.refresh(true)">
    <template v-if="ov">
      <Callout v-if="ov.diagnosis.wasted_tasks > 0" type="warning" class="gap">
        有 {{ ov.diagnosis.duplicates.length }} 个 IP 被多个任务重复探测，多出
        {{ ov.diagnosis.wasted_tasks }} 个任务在消耗探针配额。
        <template #action>
          <NButton size="small" @click="tab = 'tasks'">查看并清理</NButton>
        </template>
      </Callout>

      <NTabs v-model:value="tab" type="line" animated>
        <NTabPane name="nodes" :tab="`节点 ${ov.tasks.length}`">
          <NCard size="small" content-style="padding: 0">
            <NEmpty v-if="!ov.tasks.length" description="还没有拨测任务" class="pad" />
            <table v-else class="grid">
              <thead>
                <tr><th>节点</th><th>近 24 小时</th><th>可用率</th><th>所属模板</th><th>当前</th></tr>
              </thead>
              <tbody>
                <tr v-for="t in ov.tasks" :key="t.uuid">
                  <td>
                    <span class="row nowrap">
                      <IpBadge :item="t.target" :show-status="false" />
                      <IpNameEditor :ip="t.target.ip" :name="t.target.name" @saved="changed" />
                    </span>
                    <div v-if="t.target.geo.org" class="muted small org">{{ t.target.geo.org }}</div>
                  </td>
                  <td><UptimeBar :samples="hist.data.value?.samples[t.target.ip] ?? []" /></td>
                  <td class="num">
                    {{ fmtPercent(hist.data.value?.stats[t.target.ip]?.uptime) }}
                    <div class="muted small">{{ hist.data.value?.stats[t.target.ip]?.samples ?? 0 }} 次采样</div>
                  </td>
                  <td class="sub small">{{ t.template_name || '—' }}</td>
                  <td><StatusDot :status="t.target.probe?.status" label /></td>
                </tr>
              </tbody>
            </table>
          </NCard>
        </NTabPane>

        <NTabPane name="templates" :tab="`模板 ${ov.templates.length}`">
          <NCard size="small" content-style="padding: 0">
            <NEmpty v-if="!ov.templates.length" description="还没有拨测模板" class="pad" />
            <table v-else class="grid">
              <thead>
                <tr><th>模板</th><th>探测方式</th><th class="r">任务</th><th class="r">被引用</th><th>实测结果</th></tr>
              </thead>
              <tbody>
                <tr v-for="t in ov.templates" :key="t.uuid">
                  <td>
                    <div>{{ t.name }}</div>
                    <div v-if="t.description" class="muted small">{{ t.description }}</div>
                  </td>
                  <td>
                    <div class="mono small">{{ t.method }} {{ t.url_hint }}</div>
                    <div class="muted small">{{ t.host_hint }} · 每 {{ t.interval ?? '—' }} 秒</div>
                  </td>
                  <td class="r num">{{ t.task_count }}</td>
                  <td class="r num">{{ t.referenced_count }}</td>
                  <td>
                    <NTag size="small" :type="healthText(t.health).type" :bordered="false">
                      {{ healthText(t.health).text }}
                    </NTag>
                  </td>
                </tr>
              </tbody>
            </table>
          </NCard>
        </NTabPane>

        <NTabPane name="tasks" :tab="`任务 ${ov.tasks.length}`">
          <NCard size="small" content-style="padding: 0">
            <template #header>
              <div class="row">
                <span class="small sub">清理重复任务时优先保留</span>
                <NSelect v-model:value="keepTemplate" :options="templateOptions" clearable
                  placeholder="任意一个" size="small" style="width: 240px" />
                <NButton size="small" type="error" ghost :loading="pending === 'cleanup'"
                  :disabled="!ov.diagnosis.wasted_tasks" @click="cleanup">
                  清理重复任务
                </NButton>
              </div>
            </template>
            <table class="grid">
              <thead>
                <tr><th>任务</th><th>目标</th><th>模板</th><th>状态</th><th /></tr>
              </thead>
              <tbody>
                <tr v-for="t in ov.tasks" :key="t.uuid">
                  <td class="small">{{ t.name }}</td>
                  <td><IpBadge :item="t.target" compact /></td>
                  <td class="sub small">{{ t.template_name || '—' }}</td>
                  <td>
                    <NTag size="small" :type="t.enabled ? 'success' : 'default'" :bordered="false">
                      {{ t.enabled ? '启用' : '停用' }}
                    </NTag>
                    <NTag v-if="ov.diagnosis.duplicates.some((x) => x.ip === t.target.ip)" size="small"
                      type="warning" :bordered="false">重复</NTag>
                  </td>
                  <td class="r">
                    <NButton quaternary size="tiny" :loading="pending === `task:${t.uuid}`"
                      @click="deleteTask(t.uuid, t.name)">
                      <Trash2 :size="13" />
                    </NButton>
                  </td>
                </tr>
                <tr v-if="!ov.tasks.length"><td colspan="5" class="muted pad">没有拨测任务</td></tr>
              </tbody>
            </table>
          </NCard>
        </NTabPane>

        <NTabPane name="wizard" tab="统一探针">
          <div class="stack">
            <p class="prose">
              官方模板通常用 HTTPS 探测目标 IP，自建服务器上证书对不上就会一直显示不可用。
              统一探针的做法：每台节点上放一个极简的 HTTP 应答端点，所有规则共用一个模板，
              探针连的是地址池里的 IP，测试域名只作为 Host 头，不需要真的配 DNS。
            </p>

            <NCard title="1 · 在每台节点上部署应答端点" size="small">
              <NForm label-placement="left" :show-feedback="false" label-width="auto">
                <NFormItem label="测试域名">
                  <NInput v-model:value="wizard.host" placeholder="probe.example.com" style="max-width: 320px" />
                </NFormItem>
              </NForm>
              <div class="conf">
                <pre class="code">{{ responderConf }}</pre>
                <NButton size="small" class="copy" @click="copyConf">
                  <template #icon><Copy :size="13" /></template>
                  复制
                </NButton>
              </div>
              <p class="muted small">
                不想改现有 Nginx 的话，仓库里的 <code>probe-responder/install.sh</code> 可以一键起一个独立的应答容器。
                部署后在节点上自检：<code>curl -sI -H 'Host: {{ hostForConf }}' http://127.0.0.1:{{ wizard.port }}{{ wizard.path }}</code>
              </p>
            </NCard>

            <NCard title="2 · 创建统一模板" size="small">
              <NForm label-placement="top" :show-feedback="false" class="form">
                <div class="grid-2">
                  <NFormItem label="模板名称"><NInput v-model:value="wizard.name" maxlength="50" /></NFormItem>
                  <NFormItem label="蓝本模板（继承它的探测点）">
                    <NSelect v-model:value="wizard.base" :options="templateOptions" />
                  </NFormItem>
                </div>
                <div class="grid-3">
                  <NFormItem label="协议">
                    <NRadioGroup v-model:value="wizard.scheme">
                      <NRadioButton value="http">HTTP</NRadioButton>
                      <NRadioButton value="https">HTTPS</NRadioButton>
                    </NRadioGroup>
                  </NFormItem>
                  <NFormItem label="端口">
                    <NInputNumber v-model:value="wizard.port" :min="1" :max="65535" style="width: 100%" />
                  </NFormItem>
                  <NFormItem label="方法">
                    <NRadioGroup v-model:value="wizard.method">
                      <NRadioButton value="HEAD">HEAD</NRadioButton>
                      <NRadioButton value="GET">GET</NRadioButton>
                    </NRadioGroup>
                  </NFormItem>
                </div>
                <div class="grid-2">
                  <NFormItem label="路径"><NInput v-model:value="wizard.path" class="mono" /></NFormItem>
                  <NFormItem label="Host">
                    <NRadioGroup v-model:value="wizard.hostMode">
                      <NRadioButton value="custom">测试域名</NRadioButton>
                      <NRadioButton value="follow_target">目标 IP</NRadioButton>
                    </NRadioGroup>
                  </NFormItem>
                </div>
              </NForm>
              <NButton type="primary" :loading="pending === 'tpl'"
                :disabled="!wizard.base || (wizard.hostMode === 'custom' && !wizard.host.trim())"
                @click="createTemplate">
                创建模板
              </NButton>
            </NCard>

            <NCard title="3 · 应用到规则" size="small">
              <NForm label-placement="top" :show-feedback="false" class="form">
                <NFormItem label="模板">
                  <NSelect v-model:value="wizard.applyTemplate" :options="templateOptions" style="max-width: 360px" />
                </NFormItem>
                <NFormItem label="规则">
                  <NCheckboxGroup v-model:value="wizard.rules">
                    <div class="rule-list">
                      <NCheckbox v-for="r in ov.rules" :key="r.uuid" :value="r.uuid">
                        <span class="row nowrap">
                          <LineTag :label="r.geo_isp_label" :region="r.geo_isp_region" />
                          <span class="mono small sub">{{ r.domain }}</span>
                          <NTag v-if="r.probe_template_uuid === wizard.applyTemplate" size="small" :bordered="false">
                            已在使用
                          </NTag>
                        </span>
                      </NCheckbox>
                    </div>
                  </NCheckboxGroup>
                </NFormItem>
              </NForm>
              <NButton type="primary" :loading="pending === 'apply'"
                :disabled="!wizard.applyTemplate || !wizard.rules.length" @click="applyTemplate">
                应用到 {{ wizard.rules.length }} 条规则
              </NButton>
            </NCard>
          </div>
        </NTabPane>
      </NTabs>
    </template>
  </QueryState>
</template>

<style scoped>
.gap {
  margin-bottom: 12px;
}

.pad {
  padding: 28px;
  text-align: center;
}

.grid {
  width: 100%;
  border-collapse: collapse;
}

.grid th {
  text-align: left;
  font-weight: 500;
  font-size: 12.5px;
  color: var(--text-3);
  padding: 8px 12px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
}

.grid td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-soft);
  vertical-align: middle;
}

.grid tr:last-child td {
  border-bottom: none;
}

.r {
  text-align: right;
}

.nowrap {
  flex-wrap: nowrap;
}

.org {
  margin-top: 2px;
}

.conf {
  position: relative;
  margin: 12px 0;
}

.copy {
  position: absolute;
  top: 8px;
  right: 8px;
}

.form :deep(.n-form-item) {
  margin-bottom: 12px;
}

.rule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
