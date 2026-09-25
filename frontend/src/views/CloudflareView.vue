<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NInput, NTag } from 'naive-ui'
import { ExternalLink, RefreshCw, Trash2 } from 'lucide-vue-next'
import { api, type CfRecord } from '@/api'
import PageHeader from '@/components/ui/PageHeader.vue'
import StatusDot from '@/components/ui/StatusDot.vue'
import { useAction } from '@/composables/useAction'
import { loadMeta } from '@/composables/useMeta'
import { invalidate, useResource } from '@/composables/useResource'

const status = useResource('cloudflare:status', () => api.cloudflare.status())
const overview = useResource('cloudflare:overview', (fresh) => api.cloudflare.overview({ fresh }))
const { run, pending, confirm } = useAction()

const token = ref('')
const configured = computed(() => status.data.value?.token.configured ?? false)
const editable = computed(() => status.data.value?.token.editable ?? true)

function changed() {
  invalidate('cloudflare', 'dashboard')
  void loadMeta()
}

async function saveToken() {
  const r = await run('save', () => api.cloudflare.setToken(token.value.trim()), (x) => x.message)
  if (r) {
    token.value = ''
    changed()
  }
}

async function clearToken() {
  const ok = await confirm({
    title: '清除 Cloudflare Token',
    content: '清除后将无法代你创建或删除 Cloudflare 记录，已创建的记录不受影响。',
    positiveText: '清除',
    danger: true,
  })
  if (ok && (await run('clear', () => api.cloudflare.clearToken(), '已清除')) !== undefined) changed()
}

async function deleteRecord(r: CfRecord) {
  const ok = await confirm({
    title: '删除 Cloudflare 记录',
    content: `删除 ${r.name} → ${r.content}？该域名的解析会立即失效。`,
    positiveText: '删除',
    danger: true,
  })
  if (ok && (await run(`del:${r.id}`, () => api.cloudflare.deleteRecord(r.zone_id, r.id), '记录已删除')) !== undefined) {
    changed()
  }
}
</script>

<template>
  <PageHeader
    title="Cloudflare"
    description="AxisNow 调度域不直接给访客使用，需要在你自己的域名上加一条 CNAME 指向它。配好 Token 后可以在「域名与规则」里一键完成。"
  >
    <template #actions>
      <NButton :loading="overview.refreshing.value" @click="status.refresh(); overview.refresh(true)">
        <template #icon><RefreshCw :size="14" /></template>
        刷新
      </NButton>
    </template>
  </PageHeader>

  <div class="layout">
    <div class="stack">
      <NCard title="已接入的记录" size="small" content-style="padding: 0">
        <template #header-extra>
          <span class="muted small">指向 AxisNow 调度域的 CNAME</span>
        </template>
        <NAlert v-if="overview.error.value" type="error" :show-icon="false" class="pad">
          {{ overview.error.value }}
        </NAlert>
        <NEmpty v-else-if="!configured" description="配置 Token 后显示" class="pad" />
        <NEmpty v-else-if="!overview.data.value?.links.length" class="pad"
          description="还没有记录指向 AxisNow 调度域" />
        <table v-else class="grid">
          <thead>
            <tr><th>记录</th><th>指向</th><th>代理</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="r in overview.data.value.links" :key="r.id">
              <td>
                <div class="mono">{{ r.name }}</div>
                <div class="muted small">{{ r.zone_name }} · {{ r.type }}</div>
              </td>
              <td class="mono small">{{ r.content }}</td>
              <td>
                <NTag v-if="r.proxied" size="small" type="error" :bordered="false">已开代理 · 调度失效</NTag>
                <NTag v-else size="small" :bordered="false">仅 DNS</NTag>
              </td>
              <td class="r">
                <NButton quaternary size="tiny" :loading="pending === `del:${r.id}`" @click="deleteRecord(r)">
                  <Trash2 :size="13" />
                </NButton>
              </td>
            </tr>
          </tbody>
        </table>
      </NCard>

      <NCard v-if="configured" title="Token 可见的域名" size="small">
        <NEmpty v-if="!overview.data.value?.zones.length" description="没有可见的域名" />
        <div v-else class="zones">
          <div v-for="z in overview.data.value.zones" :key="z.id" class="row">
            <StatusDot :status="z.status === 'active' ? 'available' : 'unknown'" />
            <span class="mono">{{ z.name }}</span>
            <span class="muted small">{{ z.account }}</span>
          </div>
        </div>
      </NCard>
    </div>

    <div class="stack">
      <NCard title="API Token" size="small">
        <template #header-extra>
          <span class="row">
            <StatusDot :status="status.data.value?.verified ? 'available' : configured ? 'unavailable' : null" />
            <span class="small sub">{{ status.data.value?.message ?? '读取中…' }}</span>
          </span>
        </template>
        <NAlert v-if="!editable" type="info" :show-icon="false">
          Token 由环境变量 <code>CLOUDFLARE_API_TOKEN</code> 提供。
        </NAlert>
        <template v-else>
          <NInput v-model:value="token" type="password" show-password-on="click"
            :placeholder="configured ? '输入新 Token 以替换' : '粘贴 Token'"
            :input-props="{ autocomplete: 'off' }" />
          <div class="row actions">
            <NButton type="primary" :loading="pending === 'save'" :disabled="token.trim().length < 20"
              @click="saveToken">
              保存并校验
            </NButton>
            <NButton v-if="configured" type="error" ghost :loading="pending === 'clear'" @click="clearToken">
              清除
            </NButton>
          </div>
          <p class="muted small">Token 只保存在服务器上，页面和接口都不会回显。</p>
        </template>
      </NCard>

      <NCard title="如何创建 Token" size="small">
        <ol class="steps small">
          <li>
            打开
            <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" rel="noopener">
              API Tokens <ExternalLink :size="11" />
            </a>
            ，点 <b>Create Token</b>。
          </li>
          <li>选择模板 <b>Edit zone DNS</b>（或手动添加权限 <code>Zone → DNS → Edit</code>）。</li>
          <li><b>Zone Resources</b> 选 Include → Specific zone，只勾需要的域名。</li>
          <li>创建后立即复制 Token（只显示一次），粘贴到上面。</li>
        </ol>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}

.pad {
  margin: 16px;
  padding: 16px;
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
}

.grid tr:last-child td {
  border-bottom: none;
}

.r {
  text-align: right;
}

.zones {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.actions {
  margin: 10px 0 6px;
}

@media (max-width: 1100px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
