// 国家/地区中文名：直接用浏览器内置的 Intl.DisplayNames，不维护对照表
let names: Intl.DisplayNames | null = null

export function countryName(code: string): string {
  try {
    names ??= new Intl.DisplayNames(['zh-CN'], { type: 'region' })
    return names.of(code.toUpperCase()) ?? code.toUpperCase()
  } catch {
    return code.toUpperCase()
  }
}
