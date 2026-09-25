import { createRouter, createWebHistory } from 'vue-router'
import { api } from '@/api'
import { setUnauthorizedHandler } from '@/api/http'
import { loadMeta, useMeta } from '@/composables/useMeta'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('@/views/DashboardView.vue') },
    { path: '/domains', component: () => import('@/views/DomainsView.vue') },
    { path: '/scheduling', component: () => import('@/views/SchedulingView.vue') },
    { path: '/rules/:uuid', component: () => import('@/views/RuleView.vue'), props: true },
    { path: '/probe', component: () => import('@/views/ProbeView.vue') },
    { path: '/cloudflare', component: () => import('@/views/CloudflareView.vue') },
    { path: '/settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

let authChecked = false

router.beforeEach(async (to) => {
  if (!authChecked) {
    authChecked = true
    const state = await api.auth.state().catch(() => null)
    if (state?.authenticated) await loadMeta()
    else if (!to.meta.public) return { path: '/login', query: { next: to.fullPath } }
  }
  if (!to.meta.public && !useMeta().meta.value) {
    // 登录后第一次进入受保护页面
    if (!(await loadMeta())) return { path: '/login', query: { next: to.fullPath } }
  }
  return true
})

setUnauthorizedHandler(() => {
  useMeta().meta.value = null
  if (router.currentRoute.value.path !== '/login') {
    void router.replace({ path: '/login', query: { next: router.currentRoute.value.fullPath } })
  }
})
