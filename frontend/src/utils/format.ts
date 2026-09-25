const pad = (n: number) => String(n).padStart(2, '0')

/** 2026-09-25 17:33 */
export function fmtTime(iso?: string | null, withSeconds = false): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const base = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return withSeconds ? `${base}:${pad(d.getSeconds())}` : base
}

/** 「3 分钟前」 */
export function fmtRelative(iso?: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const s = Math.round((Date.now() - t) / 1000)
  if (s < 45) return '刚刚'
  if (s < 3600) return `${Math.round(s / 60)} 分钟前`
  if (s < 86400) return `${Math.round(s / 3600)} 小时前`
  return `${Math.round(s / 86400)} 天前`
}

export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function fmtDays(days?: number[]): string {
  if (!days || days.length === 0 || days.length === 7) return '每天'
  const sorted = [...days].sort((a, b) => a - b)
  if (sorted.join() === '0,1,2,3,4') return '工作日'
  if (sorted.join() === '5,6') return '周末'
  return sorted.map((d) => WEEKDAYS[d]).join('、')
}

export function fmtPercent(v?: number | null): string {
  return v === null || v === undefined ? '—' : `${v % 1 === 0 ? v : v.toFixed(1)}%`
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
