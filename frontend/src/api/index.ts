import { request } from './http'
import type {
  ApplyEvent,
  AuthState,
  CfRecord,
  CfZone,
  Dashboard,
  Domain,
  Meta,
  Options,
  ProbeHistory,
  ProbeOverview,
  Rule,
  SchedulerState,
  TickResult,
  TideSlot,
  TokenMeta,
} from './types'

export * from './types'
export { ApiError } from './http'

const enc = encodeURIComponent
type Fresh = { fresh?: boolean }
const q = (o?: Fresh) => (o?.fresh ? { fresh: 1 } : undefined)

export const api = {
  auth: {
    state: () => request<AuthState>('/auth/state'),
    login: (password: string) => request('/auth/login', { method: 'POST', body: { password } }),
    setup: (password: string, confirm: string) =>
      request('/auth/setup', { method: 'POST', body: { password, confirm } }),
    logout: () => request('/auth/logout', { method: 'POST' }),
  },

  meta: () => request<Meta>('/meta'),
  dashboard: (o?: Fresh) => request<Dashboard>('/dashboard', { query: q(o) }),
  events: () => request<{ events: ApplyEvent[] }>('/events'),
  setIpLabel: (ip: string, name: string) =>
    request('/ip-labels', { method: 'PUT', body: { ip, name } }),

  rules: {
    list: (o?: Fresh) =>
      request<{ rules: Rule[]; scheduler: SchedulerState }>('/rules', { query: q(o) }),
    get: (uuid: string, o?: Fresh) =>
      request<{ rule: Rule }>(`/rules/${enc(uuid)}`, { query: q(o) }),
    create: (body: Record<string, unknown>) =>
      request<{ rule: Rule }>('/rules', { method: 'POST', body }),
    update: (uuid: string, body: Record<string, unknown>) =>
      request(`/rules/${enc(uuid)}`, { method: 'PUT', body }),
    remove: (uuid: string) =>
      request(`/rules/${enc(uuid)}`, { method: 'DELETE', body: { confirm: true } }),
    adopt: (uuid: string) => request(`/rules/${enc(uuid)}/adopt`, { method: 'POST' }),
    release: (uuid: string) => request(`/rules/${enc(uuid)}/release`, { method: 'POST' }),
    setEnabled: (uuid: string, enabled: boolean) =>
      request(`/rules/${enc(uuid)}/enabled`, { method: 'POST', body: { enabled } }),
    setNote: (uuid: string, ip: string, note: string) =>
      request(`/rules/${enc(uuid)}/notes`, { method: 'POST', body: { ip, note } }),
    setFeatureEnabled: (uuid: string, fid: string, enabled: boolean) =>
      request(`/rules/${enc(uuid)}/features/${enc(fid)}/enabled`, {
        method: 'POST',
        body: { enabled },
      }),
    patchFeature: (uuid: string, fid: string, config: Record<string, unknown>) =>
      request(`/rules/${enc(uuid)}/features/${enc(fid)}/config`, {
        method: 'POST',
        body: { config },
      }),
    apply: (uuid: string) =>
      request<{ order: string[]; slot_name: string | null }>(`/rules/${enc(uuid)}/apply`, {
        method: 'POST',
      }),
    sync: (uuid: string) => request(`/rules/${enc(uuid)}/sync`, { method: 'POST' }),
  },

  tide: {
    saveSlot: (uuid: string, slot: Partial<TideSlot>) =>
      request<{ slot: TideSlot }>(`/rules/${enc(uuid)}/tide/slots`, { method: 'POST', body: slot }),
    deleteSlot: (uuid: string, id: string) =>
      request(`/rules/${enc(uuid)}/tide/slots/${enc(id)}`, { method: 'DELETE' }),
    reorderSlots: (uuid: string, ids: string[]) =>
      request(`/rules/${enc(uuid)}/tide/slots/reorder`, { method: 'POST', body: { ids } }),
    setSlotIps: (uuid: string, id: string, ips: string[]) =>
      request(`/rules/${enc(uuid)}/tide/slots/${enc(id)}/ips`, { method: 'POST', body: { ips } }),
    setBaseOrder: (uuid: string, ips: string[]) =>
      request(`/rules/${enc(uuid)}/tide/order`, { method: 'POST', body: { ips } }),
  },

  tick: () => request<{ result: TickResult }>('/scheduler/tick', { method: 'POST' }),

  domains: {
    list: (o?: Fresh) => request<{ domains: Domain[] }>('/domains', { query: q(o) }),
    create: (body: Record<string, unknown>) =>
      request<{ domain: { domain: string } }>('/domains', { method: 'POST', body }),
    remove: (uuid: string) =>
      request(`/domains/${enc(uuid)}`, { method: 'DELETE', body: { confirm: true } }),
    checkRecords: (body: Record<string, unknown>) =>
      request<{ result: unknown }>('/domains/check-records', { method: 'POST', body }),
  },

  options: () => request<Options>('/options'),

  probe: {
    overview: (o?: Fresh) => request<ProbeOverview>('/probe/overview', { query: q(o) }),
    history: () => request<ProbeHistory>('/probe/history'),
    createTemplate: (body: Record<string, unknown>) =>
      request<{ template: { uuid: string; name: string } }>('/probe/templates', {
        method: 'POST',
        body,
      }),
    apply: (template_uuid: string, rule_uuids: string[]) =>
      request<{ applied: number; failed: number; results: { uuid: string; ok: boolean; error?: string }[] }>(
        '/probe/apply',
        { method: 'POST', body: { template_uuid, rule_uuids } },
      ),
    deleteTask: (uuid: string) => request(`/probe/tasks/${enc(uuid)}`, { method: 'DELETE' }),
    cleanup: (keep_template_uuid: string) =>
      request<{ deleted: unknown[]; kept: number; failures: unknown[] }>('/probe/tasks/cleanup', {
        method: 'POST',
        body: { keep_template_uuid, confirm: true },
      }),
  },

  cloudflare: {
    status: () =>
      request<{ token: TokenMeta; verified: boolean; message: string; need_permission?: boolean }>(
        '/cloudflare/status',
      ),
    setToken: (token: string) =>
      request<{ message: string }>('/cloudflare/token', { method: 'PUT', body: { token } }),
    clearToken: () => request('/cloudflare/token', { method: 'DELETE' }),
    zones: () => request<{ zones: CfZone[] }>('/cloudflare/zones'),
    linked: (target: string) =>
      request<{ records: CfRecord[] }>('/cloudflare/linked', { query: { target } }),
    overview: (o?: Fresh) =>
      request<{ configured: boolean; zones: CfZone[]; links: CfRecord[] }>('/cloudflare/overview', {
        query: q(o),
      }),
    createRecord: (body: Record<string, unknown>) =>
      request<{ record: CfRecord }>('/cloudflare/records', { method: 'POST', body }),
    deleteRecord: (zoneId: string, recordId: string) =>
      request(`/cloudflare/records/${enc(zoneId)}/${enc(recordId)}`, {
        method: 'DELETE',
        body: { confirm: true },
      }),
  },

  settings: {
    setToken: (token: string) =>
      request<{ message: string }>('/settings/token', { method: 'PUT', body: { token } }),
    clearToken: () => request('/settings/token', { method: 'DELETE' }),
    setScheduler: (enabled: boolean, interval_seconds: number) =>
      request('/settings/scheduler', { method: 'PUT', body: { enabled, interval_seconds } }),
    setPassword: (old: string, next: string) =>
      request('/settings/password', { method: 'PUT', body: { old, new: next } }),
  },
}
