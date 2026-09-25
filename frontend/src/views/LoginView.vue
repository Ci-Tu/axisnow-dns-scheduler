<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { api } from '@/api'
import { loadMeta } from '@/composables/useMeta'

const route = useRoute()
const router = useRouter()

const setup = ref(false)
const days = ref(180)
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  const state = await api.auth.state().catch(() => null)
  if (!state) return
  if (state.authenticated) return finish()
  setup.value = state.setup_required
  days.value = state.session_days
})

async function finish() {
  await loadMeta()
  const next = typeof route.query.next === 'string' && route.query.next.startsWith('/')
    ? route.query.next
    : '/'
  router.replace(next)
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    if (setup.value) await api.auth.setup(password.value, confirm.value)
    else await api.auth.login(password.value)
    await finish()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="panel">
      <div class="brand">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        <div>
          <div class="name">AxisNow Scheduler</div>
          <div class="muted small">DNS 路由调度控制台</div>
        </div>
      </div>

      <h2>{{ setup ? '设置访问密码' : '登录' }}</h2>
      <p class="muted small">
        {{ setup ? '首次使用，请设置一个至少 8 位的访问密码。' : `登录后 ${days} 天内保持在线，容器重启也不会掉线。` }}
      </p>

      <NForm @submit.prevent="submit">
        <NFormItem label="密码" :show-feedback="false" class="item">
          <NInput
            v-model:value="password"
            type="password"
            show-password-on="click"
            :input-props="{ autocomplete: setup ? 'new-password' : 'current-password' }"
            autofocus
            @keyup.enter="!setup && submit()"
          />
        </NFormItem>
        <NFormItem v-if="setup" label="确认密码" :show-feedback="false" class="item">
          <NInput
            v-model:value="confirm"
            type="password"
            show-password-on="click"
            :input-props="{ autocomplete: 'new-password' }"
            @keyup.enter="submit"
          />
        </NFormItem>
        <div v-if="error" class="error small">{{ error }}</div>
        <NButton type="primary" block :loading="busy" attr-type="submit" :disabled="!password">
          {{ setup ? '设置并进入' : '登录' }}
        </NButton>
      </NForm>
    </div>
  </div>
</template>

<style scoped>
.login {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 24px;
}

.panel {
  width: 100%;
  max-width: 360px;
  padding: 28px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
}

.name {
  font-weight: 600;
}

h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

h2 + p {
  margin: 4px 0 20px;
}

.item {
  margin-bottom: 14px;
}

.error {
  color: var(--err);
  margin-bottom: 12px;
}
</style>
