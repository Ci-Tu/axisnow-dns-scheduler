import { h } from 'vue'
import type { SelectGroupOption, SelectOption } from 'naive-ui'
import type { GeoOption, Options } from '@/api'
import LineTag from '@/components/ui/LineTag.vue'

const GROUP_ORDER = ['', '地域', '运营商', '搜索引擎', '云厂商', '其它']
const PREFER = ['default', 'internal', 'oversea']

// 与后端 constants.GEO_ISP_REGION 对应，用于下拉里的国旗
const CN = new Set(['internal', 'domestic', '3=0', 'CN', '10=0', '10=1', '10=2', '10=3'])

export function regionOf(value: string): string {
  if (CN.has(value)) return 'cn'
  if (value === 'hk-mo-tw') return 'hk'
  if (value === 'EU' || value === 'EUR') return 'eu'
  return 'world'
}

/** 合并各服务商的线路表（self-hosted 优先），去重并排序 */
export function collectGeoOptions(opts: Options, providerType?: string): GeoOption[] {
  const seen = new Set<string>()
  const out: GeoOption[] = []
  const keys = [providerType ?? '', 'self-hosted', ...Object.keys(opts.geo_isp)].filter(Boolean)
  for (const k of keys) {
    for (const o of opts.geo_isp[k] ?? []) {
      if (seen.has(o.value)) continue
      seen.add(o.value)
      out.push(o)
    }
  }
  const rank = (v: string) => (PREFER.includes(v) ? PREFER.indexOf(v) : 99)
  return out.sort((a, b) => rank(a.value) - rank(b.value) || a.label.localeCompare(b.label, 'zh'))
}

/** 两级下拉（分组 + 线路），每一项带国旗 */
export function geoSelectOptions(opts: Options, providerType?: string): (SelectOption | SelectGroupOption)[] {
  const groups = new Map<string, GeoOption[]>()
  for (const o of collectGeoOptions(opts, providerType)) {
    const g = GROUP_ORDER.includes(o.group) ? o.group : '其它'
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g)!.push(o)
  }
  const toOption = (o: GeoOption): SelectOption => ({
    value: o.value,
    label: o.value !== o.label ? `${o.label}（${o.value}）` : o.label,
    region: regionOf(o.value),
  })
  const result: (SelectOption | SelectGroupOption)[] = (groups.get('') ?? []).map(toOption)
  for (const g of GROUP_ORDER.filter((x) => x && groups.has(x))) {
    result.push({ type: 'group', label: g, key: g, children: groups.get(g)!.map(toOption) })
  }
  return result
}

export function renderGeoLabel(option: SelectOption | SelectGroupOption) {
  if ((option as SelectGroupOption).type === 'group') return option.label as string
  return h(LineTag, { label: String(option.label), region: String(option.region ?? 'world') })
}
