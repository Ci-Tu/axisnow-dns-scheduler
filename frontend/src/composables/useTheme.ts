import { computed, ref, watchEffect } from 'vue'
import { darkTheme, type GlobalThemeOverrides } from 'naive-ui'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'axisnow.theme'

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

const mode = ref<ThemeMode>(readMode())
const media = window.matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
media.addEventListener('change', (e) => (systemDark.value = e.matches))

const isDark = computed(() => (mode.value === 'system' ? systemDark.value : mode.value === 'dark'))

watchEffect(() => {
  document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
  try {
    localStorage.setItem(STORAGE_KEY, mode.value)
  } catch {
    /* 隐私模式下写不进去也无妨 */
  }
})

const font =
  'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
const mono = '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace'

// 克制的中性色 + 单一强调色；圆角、字号与 CSS 变量保持一致
function overrides(dark: boolean): GlobalThemeOverrides {
  const primary = dark ? '#6b8cff' : '#2f54eb'
  return {
    common: {
      fontFamily: font,
      fontFamilyMono: mono,
      fontSize: '13.5px',
      fontSizeMedium: '13.5px',
      borderRadius: '6px',
      primaryColor: primary,
      primaryColorHover: dark ? '#86a0ff' : '#4a6cf0',
      primaryColorPressed: dark ? '#5576f0' : '#2345cc',
      primaryColorSuppl: primary,
      successColor: dark ? '#3fb27f' : '#16a34a',
      warningColor: dark ? '#e0a33b' : '#d97706',
      errorColor: dark ? '#f06b6b' : '#dc2626',
      bodyColor: dark ? '#0f1115' : '#f6f7f9',
      cardColor: dark ? '#16181d' : '#ffffff',
      modalColor: dark ? '#1a1d23' : '#ffffff',
      popoverColor: dark ? '#1f2229' : '#ffffff',
      tableColor: dark ? '#16181d' : '#ffffff',
      borderColor: dark ? '#2a2e36' : '#e4e6eb',
      dividerColor: dark ? '#23262d' : '#eef0f3',
    },
    Card: { borderRadius: '8px', paddingMedium: '16px 18px', titleFontSizeMedium: '14px' },
    DataTable: {
      thColor: dark ? '#1a1d23' : '#fafbfc',
      thFontWeight: '500',
      thTextColor: dark ? '#9aa1ad' : '#6b7280',
      tdPaddingMedium: '10px 12px',
      thPaddingMedium: '9px 12px',
    },
    Button: { fontWeight: '500' },
    Tag: { borderRadius: '4px' },
  }
}

export function useTheme() {
  return {
    mode,
    isDark,
    naiveTheme: computed(() => (isDark.value ? darkTheme : null)),
    overrides: computed(() => overrides(isDark.value)),
    cycle() {
      mode.value = mode.value === 'system' ? 'light' : mode.value === 'light' ? 'dark' : 'system'
    },
  }
}
