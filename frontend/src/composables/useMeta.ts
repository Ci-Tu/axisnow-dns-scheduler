import { shallowRef } from 'vue'
import { api, type Meta } from '@/api'

// 全局元信息（版本、时区、Token 状态等），登录后加载一次，设置变更后刷新
const meta = shallowRef<Meta | null>(null)

export async function loadMeta(): Promise<Meta | null> {
  try {
    meta.value = await api.meta()
  } catch {
    /* 未登录或网络问题时保持为空 */
  }
  return meta.value
}

export function useMeta() {
  return { meta, loadMeta }
}
