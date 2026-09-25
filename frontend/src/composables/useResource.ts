import { onBeforeUnmount, onMounted, ref, shallowRef, type Ref, type ShallowRef } from 'vue'

// 页面级 stale-while-revalidate：回到访问过的页面时立即显示上次的数据，同时在后台刷新。
// 后端本身也有缓存，两层叠加后页面切换基本是瞬时的。

interface Entry {
  data: unknown
  at: number
}

const cache = new Map<string, Entry>()
const listeners = new Map<string, Set<() => void>>()

/** 写操作之后调用：让以 prefix 开头的资源失效并通知正在显示它们的页面重新拉取 */
export function invalidate(...prefixes: string[]): void {
  for (const key of [...cache.keys()]) {
    if (prefixes.some((p) => key.startsWith(p))) cache.delete(key)
  }
  for (const [key, fns] of listeners) {
    if (prefixes.some((p) => key.startsWith(p))) fns.forEach((fn) => fn())
  }
}

export interface Resource<T> {
  data: ShallowRef<T | null>
  error: Ref<string>
  loading: Ref<boolean>
  refreshing: Ref<boolean>
  refresh: (fresh?: boolean) => Promise<void>
}

export function useResource<T>(
  key: string,
  fetcher: (fresh: boolean) => Promise<T>,
  opts: { pollMs?: number } = {},
): Resource<T> {
  const hit = cache.get(key)
  const data = shallowRef<T | null>((hit?.data as T) ?? null)
  const error = ref('')
  const loading = ref(!hit)
  const refreshing = ref(false)
  let timer: number | undefined
  let seq = 0

  async function refresh(fresh = false): Promise<void> {
    const mine = ++seq
    refreshing.value = true
    try {
      const value = await fetcher(fresh)
      if (mine !== seq) return
      data.value = value
      error.value = ''
      cache.set(key, { data: value, at: Date.now() })
    } catch (e) {
      if (mine !== seq) return
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (mine === seq) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  const onInvalidate = () => void refresh()

  onMounted(() => {
    void refresh()
    if (!listeners.has(key)) listeners.set(key, new Set())
    listeners.get(key)!.add(onInvalidate)
    if (opts.pollMs) timer = window.setInterval(() => void refresh(), opts.pollMs)
  })
  onBeforeUnmount(() => {
    listeners.get(key)?.delete(onInvalidate)
    if (timer) window.clearInterval(timer)
  })

  return { data, error, loading, refreshing, refresh }
}
