<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NTooltip } from 'naive-ui'
import {
  Activity,
  Cloud,
  Globe2,
  LayoutDashboard,
  LogOut,
  Monitor,
  Moon,
  Route as RouteIcon,
  Settings,
  Sun,
} from 'lucide-vue-next'
import { api } from '@/api'
import { useMeta } from '@/composables/useMeta'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const router = useRouter()
const { meta } = useMeta()
const theme = useTheme()

interface NavItem {
  to: string
  label: string
  icon: Component
}

const nav: NavItem[] = [
  { to: '/', label: '仪表盘', icon: LayoutDashboard },
  { to: '/domains', label: '域名与规则', icon: Globe2 },
  { to: '/scheduling', label: '调度', icon: RouteIcon },
  { to: '/probe', label: '拨测', icon: Activity },
  { to: '/cloudflare', label: 'Cloudflare', icon: Cloud },
  { to: '/settings', label: '设置', icon: Settings },
]

function isActive(to: string): boolean {
  if (to === '/') return route.path === '/'
  return route.path === to || route.path.startsWith(`${to}/`) ||
    (to === '/scheduling' && route.path.startsWith('/rules/'))
}

// 右下角时钟显示调度时区的时间（潮汐时间段按这个时区生效）
const now = ref(new Date())
let timer: number | undefined
onMounted(() => (timer = window.setInterval(() => (now.value = new Date()), 1000)))
onBeforeUnmount(() => window.clearInterval(timer))

const clock = computed(() => {
  const tz = meta.value?.timezone ?? 'Asia/Shanghai'
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: tz,
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(now.value)
  } catch {
    return now.value.toLocaleTimeString()
  }
})

const themeIcon = computed(() =>
  theme.mode.value === 'system' ? Monitor : theme.mode.value === 'dark' ? Moon : Sun,
)
const themeLabel = computed(
  () => ({ system: '跟随系统', light: '浅色', dark: '深色' })[theme.mode.value],
)

async function logout() {
  await api.auth.logout().catch(() => undefined)
  router.replace('/login')
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand">
        <img src="/favicon.svg" alt="" width="22" height="22" />
        <span>AxisNow <b>Scheduler</b></span>
      </RouterLink>

      <nav>
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.to) }"
        >
          <component :is="item.icon" :size="16" :stroke-width="1.8" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="foot">
        <div class="clock" :title="`调度时区：${meta?.timezone ?? ''}`">
          <span class="mono">{{ clock }}</span>
          <span class="tz">{{ meta?.timezone }}</span>
        </div>
        <div class="row foot-actions">
          <NTooltip>
            <template #trigger>
              <NButton quaternary size="small" circle @click="theme.cycle()">
                <component :is="themeIcon" :size="15" />
              </NButton>
            </template>
            主题：{{ themeLabel }}
          </NTooltip>
          <NTooltip>
            <template #trigger>
              <NButton quaternary size="small" circle @click="logout">
                <LogOut :size="15" />
              </NButton>
            </template>
            退出登录
          </NTooltip>
          <span class="spacer" />
          <span class="version muted">v{{ meta?.version }}</span>
        </div>
      </div>
    </aside>

    <main class="content">
      <div class="inner">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100%;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  width: var(--sidebar-w);
  flex: none;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  border-right: 1px solid var(--border);
  background: var(--surface);
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 4px 8px 18px;
  color: var(--text);
  font-size: 14px;
  text-decoration: none;
}

.brand b {
  font-weight: 600;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 10px;
  border-radius: 6px;
  color: var(--text-2);
  text-decoration: none;
  transition: background-color 0.12s, color 0.12s;
}

.nav-item:hover {
  background: var(--surface-2);
  color: var(--text);
}

.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 500;
}

.foot {
  margin-top: auto;
  padding: 12px 8px 0;
  border-top: 1px solid var(--border-soft);
}

.clock {
  display: flex;
  flex-direction: column;
  margin-bottom: 8px;
}

.clock .mono {
  font-size: 15px;
  color: var(--text);
}

.tz {
  font-size: 11.5px;
  color: var(--text-3);
}

.foot-actions {
  gap: 2px;
}

.version {
  font-size: 11.5px;
}

.content {
  flex: 1;
  min-width: 0;
}

.inner {
  max-width: 1320px;
  margin: 0 auto;
  padding: 28px 32px 48px;
}

@media (max-width: 860px) {
  .shell {
    flex-direction: column;
  }

  .sidebar {
    position: static;
    height: auto;
    width: 100%;
    flex-direction: row;
    align-items: center;
    padding: 8px 12px;
    border-right: none;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }

  .brand {
    padding: 0 12px 0 0;
  }

  .brand span,
  .foot {
    display: none;
  }

  nav {
    flex-direction: row;
  }

  .nav-item span {
    display: none;
  }

  .inner {
    padding: 20px 16px 40px;
  }
}
</style>
