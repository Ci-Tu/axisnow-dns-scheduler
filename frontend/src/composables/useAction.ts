import { ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

/** 包装一个异步操作：自动管理 pending、成功提示与错误提示 */
export function useAction() {
  const message = useMessage()
  const dialog = useDialog()
  const pending = ref<string | null>(null)

  async function run<T>(
    key: string,
    fn: () => Promise<T>,
    success?: string | ((result: T) => string),
  ): Promise<T | undefined> {
    pending.value = key
    try {
      const result = await fn()
      if (success) message.success(typeof success === 'function' ? success(result) : success)
      return result
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e), { duration: 6000 })
      return undefined
    } finally {
      pending.value = null
    }
  }

  function confirm(opts: {
    title: string
    content: string
    positiveText?: string
    danger?: boolean
  }): Promise<boolean> {
    return new Promise((resolve) => {
      const d = opts.danger ? dialog.error : dialog.warning
      d({
        title: opts.title,
        content: opts.content,
        positiveText: opts.positiveText ?? '确认',
        negativeText: '取消',
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
        onMaskClick: () => resolve(false),
      })
    })
  }

  return { pending, run, confirm, message }
}
