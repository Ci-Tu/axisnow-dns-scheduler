// 与后端 /api 响应一一对应的类型定义

export type ProbeStatus = 'available' | 'unavailable' | 'unknown' | string

export interface GeoInfo {
  country: string | null // ISO 3166 小写两位码
  asn: number | null
  org: string | null
  private: boolean
}

export interface ProbeState {
  status: ProbeStatus
  latency?: number | null
}

/** 所有页面里「一个 IP」的统一表示 */
export interface IpView {
  ip: string
  name: string // 全局名称
  note: string // 规则内备注
  probe: ProbeState | null
  geo: GeoInfo
}

export interface TokenMeta {
  configured: boolean
  length: number
  source: 'env' | 'config' | ''
  editable: boolean
}

export interface FeatureInfo {
  id: string
  name: string
  description: string
  order: number
  ui: string
  default_config: Record<string, unknown>
}

export interface Meta {
  version: string
  timezone: string
  now: string
  session_days: number
  token: TokenMeta
  cloudflare: TokenMeta
  scheduler: { enabled: boolean; interval_seconds: number }
  features: FeatureInfo[]
  geoip: {
    attribution: string
    url: string
    country: { loaded: boolean; updated: number | null }
    asn: { loaded: boolean; updated: number | null }
  }
}

export interface AuthState {
  authenticated: boolean
  setup_required: boolean
  session_days: number
  version: string
}

export interface TideSlot {
  id: string
  name: string
  start: string
  end: string
  days: number[]
  ips: string[]
  enabled: boolean
  cross_midnight: boolean
}

export interface TideConfig {
  enabled: boolean
  default_ips: string[]
  slots: TideSlot[]
}

export interface FeatureCard {
  id: string
  name: string
  description: string
  ui: string
  order: number
  enabled: boolean
  applicable: boolean
  reason: string
  config: Record<string, unknown>
  summary: Record<string, unknown>
}

export interface ProbeSummary {
  known: boolean
  available: number
  unavailable: number
  total: number
  monitored?: number
  latency_avg?: number | null
}

export interface AppliedState {
  fingerprint: string
  order: string[]
  slot_name: string | null
  at: string
}

export type PoolMode = 'all_eips' | 'custom_eips' | 'custom_ips'

export interface Rule {
  uuid: string
  name: string
  description: string
  domain: string
  dns_domain_uuid: string
  record_type: string
  geo_isp: string
  geo_isp_label: string
  geo_isp_region: string
  status: string
  group_types: string[]
  election_strategy: string
  election_label: string
  ip_quantity: number | null
  trigger_interval: number | null
  edge_probe_templates: string[]
  ttl: number | null
  created_at: string
  updated_at: string
  managed: boolean
  enabled: boolean
  pool: string[]
  pool_mode: PoolMode
  eip_uuids: string[]
  ips: IpView[]
  probe_summary: ProbeSummary
  features: FeatureCard[]
  last_applied: AppliedState | null
  desired_order: string[] | null
}

export interface SchedulerState {
  running: boolean
  last_tick: string | null
  last_error: string
}

export interface Domain {
  uuid: string
  domain: string
  name: string
  record_type: string
  status: string
  provider_type: string
  provider_source: string
  zone: string
  zone_plan: string
  supports_geo_split: boolean
  rules: Rule[]
}

export interface GeoOption {
  value: string
  label: string
  group: string
  display?: string
  plan?: string
}

export interface Options {
  geo_isp: Record<string, GeoOption[]>
  probe_templates: { uuid: string; name: string; enabled: boolean }[]
  providers: { uuid: string; name: string; type: string; source: string; managed?: boolean }[]
  managed_providers: {
    uuid: string
    name: string
    type: string
    description: string
    zones: { uuid: string; name: string }[]
  }[]
  eips: (IpView & { uuid: string; tag: string; status: string })[]
  address_pool_modes: { value: PoolMode; label: string }[]
  no_all_eips_strategies: string[]
  strategies: { value: string; label: string; help: string }[]
  trigger_intervals: number[]
}

export interface ApplyEvent {
  at: string
  rule: string
  slot: string | null
  ok: boolean
  message: string
  domain?: string
  line?: string
}

export interface DashboardNode extends IpView {
  samples: number
  uptime: number | null
  avg_ms: number | null
  lines: string[]
}

export interface Dashboard {
  counts: {
    domains: number
    rules: number
    managed_rules: number
    probe_templates: number
    probe_tasks: number
  }
  domains: {
    uuid: string
    domain: string
    record_type: string
    status: string
    provider_type: string
    rules: number
  }[]
  nodes: DashboardNode[]
  events: ApplyEvent[]
  scheduler: SchedulerState & { enabled: boolean; interval_seconds: number }
  cloudflare: TokenMeta
}

export interface Sample {
  t: number
  s: ProbeStatus
  ms: number | null
}

export interface ProbeHistory {
  samples: Record<string, Sample[]>
  stats: Record<string, { samples: number; uptime: number | null; avg_ms: number | null }>
}

export interface ProbeTemplate {
  uuid: string
  name: string
  description: string
  enabled: boolean
  referenced_count: number
  interval: number | null
  task_count: number
  health: { known: boolean; total: number; available: number; unavailable: number; unknown: number }
  scheme: string
  port: number
  path: string
  method: string
  host_mode: string
  host_value: string
  url_hint: string
  host_hint: string
}

export interface ProbeOverview {
  templates: ProbeTemplate[]
  tasks: {
    uuid: string
    name: string
    enabled: boolean
    target: IpView
    template_uuid: string
    template_name: string
  }[]
  diagnosis: {
    template_count: number
    task_count: number
    distinct_targets: number
    wasted_tasks: number
    duplicates: { ip: string; count: number; templates: string[] }[]
  }
  rules: {
    uuid: string
    name: string
    domain: string
    geo_isp: string
    geo_isp_label: string
    geo_isp_region: string
    probe_template_uuid: string
  }[]
}

export interface CfZone {
  id: string
  name: string
  status: string
  type: string
  account: string | null
}

export interface CfRecord {
  id: string
  type: string
  name: string
  content: string
  proxied: boolean
  ttl: number
  comment: string | null
  zone_id: string
  zone_name?: string
  matched_domain?: string
}

export interface TickResult {
  at: string
  checked: number
  applied: number
  errors: string[]
  skipped?: string
}
