<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { api } from '@/api'
import StatusDot from '@/components/ui/StatusDot.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useAction } from '@/composables/useAction'
import { loadMeta, useMeta } from '@/composables/useMeta'
import { invalidate, useResource } from '@/composables/useResource'
import { fmtTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const { meta } = useMeta()
const { run, pending, confirm } = useAction()

const tab = ref(typeof route.query.tab === 'string' ? route.query.tab : 'axisnow')
watch(tab, (t) => router.replace({ query: { tab: t } }))

// ---------- AxisNow Token ----------
const token = ref('')
const tokenMeta = computed(() => meta.value?.token)

async function saveToken() {
  const r = await run('token', () => api.settings.setToken(token.value.trim()), (x) => x.message)
  if (r) {
    token.value = ''
    await loadMeta()
    invalidate('')
  }
}

async function clearToken() {
  const ok = await confirm({
    title: '清除 AxisNow Token',
    content: '清除后所有页面都无法读取数据，自动调度也会停止下发。',
    positiveText: '清除',
    danger: true,
  })
  if (ok && (await run('clear', () => api.settings.clearToken(), '已清除')) !== undefined) await loadMeta()
}

// ---------- 调度 ----------
const schedEnabled = ref(true)
const schedInterval = ref(30)
watch(meta, (m) => {
  if (!m) return
  schedEnabled.value = m.scheduler.enabled
  schedInterval.value = m.scheduler.interval_seconds
}, { immediate: true })

async function saveScheduler() {
  const done = await run('sched', () => api.settings.setScheduler(schedEnabled.value, schedInterval.value),
    '调度参数已保存')
  if (done !== undefined) await loadMeta()
}

// ---------- 密码 ----------
const oldPwd = ref('')
const newPwd = ref('')
async function savePassword() {
  const done = await run('pwd', () => api.settings.setPassword(oldPwd.value, newPwd.value), '密码已修改')
  if (done !== undefined) {
    oldPwd.value = ''
    newPwd.value = ''
  }
}

// ---------- 下发记录 ----------
const events = useResource('events', () => api.events().then((r) => r.events))

const geoUpdated = computed(() => {
  const t = meta.value?.geoip.country.updated
  return t ? fmtTime(new Date(t * 1000).toISOString()) : null
})
</script>

<template>
  <PageHeader title="设置" />

  <NTabs v-model:value="tab" type="line" animated>
    <NTabPane name="axisnow" tab="AxisNow">
      <div class="narrow stack">
        <NCard title="API Token" size="small">
          <template #header-extra>
            <span class="row">
              <StatusDot :status="tokenMeta?.configured ? 'available' : null" />
              <span class="small sub">
                {{ tokenMeta?.configured ? `已配置（${tokenMeta.source === 'env' ? '环境变量' : '保存在 data/config.json'}）` : '未配置' }}
              </span>
            </span>
          </template>
          <NAlert v-if="tokenMeta && !tokenMeta.editable" type="info" :show-icon="false">
            Token 由环境变量 <code>AXISNOW_API_TOKEN</code> 提供，需要修改请调整容器环境变量。
          </NAlert>
          <template v-else>
            <p class="prose small">
              在 AxisNow 控制台的 API 密钥页面创建。Token 只保存在服务器上，页面和接口都不会回显。
              保存前会先校验连通性，无效的 Token 不会覆盖原有配置。
            </p>
            <NInput v-model:value="token" type="password" show-password-on="click" class="field"
              :placeholder="tokenMeta?.configured ? '输入新 Token 以替换' : '粘贴 Token'"
              :input-props="{ autocomplete: 'off' }" />
            <div class="row">
              <NButton type="primary" :loading="pending === 'token'" :disabled="token.trim().length < 20"
                @click="saveToken">
                保存并校验
              </NButton>
              <NButton v-if="tokenMeta?.configured" type="error" ghost :loading="pending === 'clear'"
                @click="clearToken">
                清除
              </NButton>
            </div>
          </template>
        </NCard>
      </div>
    </NTabPane>

    <NTabPane name="scheduler" tab="调度">
      <div class="narrow">
        <NCard title="自动调度" size="small">
          <NForm label-placement="left" label-width="auto" :show-feedback="false" class="form">
            <NFormItem label="启用">
              <NSwitch v-model:value="schedEnabled" />
              <span class="muted small switch-hint">关闭后不再自动下发任何改动，配置全部保留</span>
            </NFormItem>
            <NFormItem label="轮询间隔">
              <NInputNumber v-model:value="schedInterval" :min="10" :max="3600" :step="5" style="width: 160px">
                <template #suffix>秒</template>
              </NInputNumber>
            </NFormItem>
            <NFormItem label="调度时区">
              <span class="mono">{{ meta?.timezone }}</span>
              <span class="muted small switch-hint">通过环境变量 <code>APP_TIMEZONE</code> 修改</span>
            </NFormItem>
          </NForm>
          <NButton type="primary" :loading="pending === 'sched'" @click="saveScheduler">保存</NButton>
        </NCard>
      </div>
    </NTabPane>

    <NTabPane name="history" tab="下发记录">
      <NCard size="small" content-style="padding: 0">
        <NEmpty v-if="!events.data.value?.length" description="还没有下发记录" class="pad" />
        <table v-else class="grid">
          <thead><tr><th>时间</th><th>时间段</th><th>结果</th><th>说明</th><th>规则</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in events.data.value" :key="i">
              <td class="mono small">{{ fmtTime(e.at, true) }}</td>
              <td>{{ e.slot || '基准顺序' }}</td>
              <td>
                <NTag size="small" :type="e.ok ? 'success' : 'error'" :bordered="false">
                  {{ e.ok ? '成功' : '失败' }}
                </NTag>
              </td>
              <td class="small sub">{{ e.message }}</td>
              <td><RouterLink :to="`/rules/${e.rule}`" class="mono small">…{{ e.rule.slice(-8) }}</RouterLink></td>
            </tr>
          </tbody>
        </table>
      </NCard>
    </NTabPane>

    <NTabPane name="security" tab="安全">
      <div class="narrow">
        <NCard title="修改访问密码" size="small">
          <NForm label-placement="top" :show-feedback="false" class="form">
            <NFormItem label="当前密码">
              <NInput v-model:value="oldPwd" type="password" :input-props="{ autocomplete: 'current-password' }" />
            </NFormItem>
            <NFormItem label="新密码（至少 8 位）">
              <NInput v-model:value="newPwd" type="password" :input-props="{ autocomplete: 'new-password' }" />
            </NFormItem>
          </NForm>
          <NButton type="primary" :loading="pending === 'pwd'" :disabled="!oldPwd || newPwd.length < 8"
            @click="savePassword">
            修改密码
          </NButton>
          <p class="muted small">登录态保持 {{ meta?.session_days }} 天，会话密钥保存在 <code>data/session.key</code>。</p>
        </NCard>
      </div>
    </NTabPane>

    <NTabPane name="about" tab="关于">
      <div class="narrow stack">
        <NCard title="功能模块" size="small">
          <div v-for="f in meta?.features" :key="f.id" class="feature">
            <div class="row">
              <b>{{ f.name }}</b>
              <NTag size="small" :bordered="false">{{ f.id }}</NTag>
              <span class="muted small">执行顺序 {{ f.order }}</span>
            </div>
            <p class="muted small">{{ f.description }}</p>
          </div>
          <p class="prose small">
            新功能只需在 <code>backend/axisnow_scheduler/features/</code> 下继承 <code>Feature</code>
            并注册，调度引擎与界面会自动识别。详见仓库的 CONTRIBUTING 文档。
          </p>
        </NCard>
        <NCard title="版本与数据" size="small">
          <dl class="kv">
            <dt>版本</dt><dd>v{{ meta?.version }}</dd>
            <dt>IP 地理数据</dt>
            <dd>
              <template v-if="meta?.geoip.country.loaded">已加载（更新于 {{ geoUpdated }}）</template>
              <span v-else class="muted">未加载，国旗暂不显示（启动后会自动下载）</span>
            </dd>
            <dt>数据来源</dt>
            <dd>
              <a :href="meta?.geoip.url" target="_blank" rel="noopener">{{ meta?.geoip.attribution }}</a>
              （CC BY 4.0）
            </dd>
          </dl>
        </NCard>
      </div>
    </NTabPane>
  </NTabs>
</template>

<style scoped>
.narrow {
  max-width: 640px;
}

.field {
  margin: 10px 0;
}

.form :deep(.n-form-item) {
  margin-bottom: 14px;
}

.switch-hint {
  margin-left: 12px;
}

.pad {
  padding: 28px;
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
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-soft);
}

.feature + .feature {
  margin-top: 12px;
}

.feature p {
  margin: 4px 0 0;
}
</style>
