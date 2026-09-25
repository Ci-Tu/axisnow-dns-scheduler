// 极简的 fetch 封装：统一错误、CSRF 头、401 跳登录

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly data: Record<string, unknown>

  constructor(message: string, status: number, data: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = typeof data.code === 'string' ? data.code : undefined
    this.data = data
  }
}

type Handler = () => void
let onUnauthorized: Handler = () => {}

export function setUnauthorizedHandler(fn: Handler): void {
  onUnauthorized = fn
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(`/api${path}`, window.location.origin)
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v))
  }
  const headers: Record<string, string> = { Accept: 'application/json' }
  const method = opts.method ?? 'GET'
  if (method !== 'GET') headers['X-Requested-With'] = 'axisnow'
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'

  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError('无法连接到服务器', 0)
  }

  let data: Record<string, unknown> = {}
  try {
    data = await res.json()
  } catch {
    throw new ApiError(`服务器返回了非 JSON 响应（HTTP ${res.status}）`, res.status)
  }
  if (res.status === 401 && data.code === 'unauthorized') {
    onUnauthorized()
  }
  if (!res.ok || data.ok === false) {
    throw new ApiError(String(data.error ?? `请求失败（HTTP ${res.status}）`), res.status, data)
  }
  return data as T
}
