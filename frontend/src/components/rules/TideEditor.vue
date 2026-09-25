<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NTag,
  NTimePicker,
} from 'naive-ui'
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { api, type FeatureCard, type Rule, type TideConfig, type TideSlot } from '@/api'
import { useAction } from '@/composables/useAction'
import { useMeta } from '@/composables/useMeta'
import { fmtDays, WEEKDAYS } from '@/utils/format'
import IpOrderEditor from './IpOrderEditor.vue'

const props = defineProps<{ rule: Rule; feature: FeatureCard }>()
const emit = defineEmits<{ changed: [] }>()

const { run, pending, confirm } = useAction()
const { meta } = useMeta()

const config = computed(() => props.feature.config as unknown as TideConfig)
const slots = computed(() => config.value.slots ?? [])
const activeId = computed(() => props.feature.summary.active_slot_id as string | undefined)
const disabled = computed(() => !props.feature.applicable)

// 基准顺序与各时间段顺序的本地草稿，保存前可以随意拖动
const baseOrder = ref<string[]>([])
const slotOrders = reactive<Record<string, string[]>>({})

watch(
  () => props.feature,
  () => {
    baseOrder.value = config.value.default_ips?.length ? [...config.value.default_ips] : [...props.rule.pool]
    for (const s of slots.value) slotOrders[s.id] = s.ips?.length ? [...s.ips] : [...props.rule.pool]
  },
  { immediate: true },
)

const baseDirty = computed(
  () => baseOrder.value.join() !== (config.value.default_ips?.length ? config.value.default_ips : props.rule.pool).join(),
)
const slotDirty = (s: TideSlot) => (slotOrders[s.id] ?? []).join() !== (s.ips?.length ? s.ips : props.rule.pool).join()

async function saveBase() {
  if (await run('base', () => api.tide.setBaseOrder(props.rule.uuid, baseOrder.value), '基准顺序已保存') !== undefined) {
    emit('changed')
  }
}

async function saveSlotOrder(s: TideSlot) {
  const done = await run(`order:${s.id}`, () => api.tide.setSlotIps(props.rule.uuid, s.id, slotOrders[s.id]),
    `「${s.name}」的顺序已保存`)
  if (done !== undefined) emit('changed')
}

async function move(s: TideSlot, delta: number) {
  const ids = slots.value.map((x) => x.id)
  const i = ids.indexOf(s.id)
  const j = i + delta
  if (j < 0 || j >= ids.length) return
  ;[ids[i], ids[j]] = [ids[j], ids[i]]
  if (await run(`move:${s.id}`, () => api.tide.reorderSlots(props.rule.uuid, ids)) !== undefined) emit('changed')
}

async function remove(s: TideSlot) {
  const ok = await confirm({ title: '删除时间段', content: `删除「${s.name}」？`, positiveText: '删除', danger: true })
  if (!ok) return
  if (await run(`del:${s.id}`, () => api.tide.deleteSlot(props.rule.uuid, s.id), '已删除') !== undefined) {
    emit('changed')
  }
}

// ---------- 新增 / 编辑时间段 ----------
const modal = reactive({ show: false, id: '', name: '', start: '09:00', end: '18:00', days: [0, 1, 2, 3, 4, 5, 6] })

function openSlot(s?: TideSlot) {
  Object.assign(modal, s
    ? { show: true, id: s.id, name: s.name, start: s.start, end: s.end, days: [...s.days] }
    : { show: true, id: '', name: '', start: '09:00', end: '18:00', days: [0, 1, 2, 3, 4, 5, 6] })
}

const crossMidnight = computed(() => modal.start > modal.end)
const allDay = computed(() => modal.start === modal.end)

async function saveSlot() {
  const existing = slots.value.find((s) => s.id === modal.id)
  const body: Partial<TideSlot> = {
    id: modal.id || undefined,
    name: modal.name.trim(),
    start: modal.start,
    end: modal.end,
    days: modal.days,
    ips: existing ? slotOrders[existing.id] : [...props.rule.pool],
  }
  if (await run('slot', () => api.tide.saveSlot(props.rule.uuid, body), '时间段已保存') !== undefined) {
    modal.show = false
    emit('changed')
  }
}
</script>

<template>
  <NCard title="潮汐调度" size="small">
    <template #header-extra>
      <span class="muted small">时间按 {{ meta?.timezone }} 计算</span>
    </template>

    <NAlert v-if="disabled" type="warning" :show-icon="false" class="block">
      当前不生效：{{ feature.reason }}
    </NAlert>

    <section class="block">
      <div class="row head">
        <h4>基准顺序</h4>
        <span class="muted small">没有时间段命中时使用。拖动调整，排在最前面的优先级最高。</span>
        <span class="spacer" />
        <NButton v-if="baseDirty" size="small" type="primary" :loading="pending === 'base'" @click="saveBase">
          保存基准顺序
        </NButton>
      </div>
      <IpOrderEditor v-model="baseOrder" :items="rule.ips" :disabled="disabled" />
    </section>

    <section>
      <div class="row head">
        <h4>时间段</h4>
        <span class="muted small">时间重叠时，列表中靠前的优先命中。</span>
        <span class="spacer" />
        <NButton size="small" :disabled="disabled" @click="openSlot()">
          <template #icon><Plus :size="14" /></template>
          新增时间段
        </NButton>
      </div>

      <NEmpty v-if="!slots.length" description="还没有时间段，全天使用基准顺序" size="small" class="empty" />
      <div v-for="(s, i) in slots" :key="s.id" class="slot" :class="{ active: s.id === activeId }">
        <div class="row slot-head">
          <span class="slot-name">{{ s.name }}</span>
          <span class="mono small sub">{{ s.start }} – {{ s.end }}</span>
          <NTag v-if="s.cross_midnight" size="small" :bordered="false">跨午夜</NTag>
          <span class="small sub">{{ fmtDays(s.days) }}</span>
          <NTag v-if="s.id === activeId" size="small" type="success" :bordered="false">此刻生效</NTag>
          <span class="spacer" />
          <NButton quaternary size="tiny" :disabled="i === 0" title="提高命中优先级" @click="move(s, -1)">
            <ArrowUp :size="13" />
          </NButton>
          <NButton quaternary size="tiny" :disabled="i === slots.length - 1" title="降低命中优先级" @click="move(s, 1)">
            <ArrowDown :size="13" />
          </NButton>
          <NButton quaternary size="tiny" title="编辑" @click="openSlot(s)"><Pencil :size="13" /></NButton>
          <NButton quaternary size="tiny" title="删除" @click="remove(s)"><Trash2 :size="13" /></NButton>
        </div>
        <div class="row slot-body">
          <IpOrderEditor v-model="slotOrders[s.id]" :items="rule.ips" :disabled="disabled" />
          <span class="spacer" />
          <NButton
            v-if="slotDirty(s)"
            size="small"
            type="primary"
            :loading="pending === `order:${s.id}`"
            @click="saveSlotOrder(s)"
          >
            保存顺序
          </NButton>
        </div>
      </div>
    </section>
  </NCard>

  <NModal
    v-model:show="modal.show"
    preset="card"
    :title="modal.id ? '编辑时间段' : '新增时间段'"
    style="width: 480px; max-width: calc(100vw - 32px)"
  >
    <NForm label-placement="top" :show-feedback="false" class="slot-form">
      <NFormItem label="名称（可选）">
        <NInput v-model:value="modal.name" maxlength="40" placeholder="例如 晚高峰" />
      </NFormItem>
      <div class="grid-2">
        <NFormItem label="开始">
          <NTimePicker v-model:formatted-value="modal.start" value-format="HH:mm" format="HH:mm"
            :actions="null" style="width: 100%" />
        </NFormItem>
        <NFormItem label="结束">
          <NTimePicker v-model:formatted-value="modal.end" value-format="HH:mm" format="HH:mm"
            :actions="null" style="width: 100%" />
        </NFormItem>
      </div>
      <p class="muted small hint">
        <template v-if="allDay">开始与结束相同表示全天。</template>
        <template v-else-if="crossMidnight">跨午夜：从所选星期的 {{ modal.start }} 持续到次日 {{ modal.end }}。</template>
        <template v-else>在所选星期的 {{ modal.start }} 至 {{ modal.end }} 生效。</template>
      </p>
      <NFormItem label="星期">
        <NCheckboxGroup v-model:value="modal.days">
          <div class="row">
            <NCheckbox v-for="(d, i) in WEEKDAYS" :key="i" :value="i" :label="d" />
          </div>
        </NCheckboxGroup>
      </NFormItem>
      <p v-if="!modal.id" class="muted small">新时间段会带入当前地址池的顺序，保存后可在列表里拖动调整。</p>
    </NForm>
    <template #footer>
      <div class="row">
        <span class="spacer" />
        <NButton @click="modal.show = false">取消</NButton>
        <NButton type="primary" :loading="pending === 'slot'" :disabled="!modal.days.length" @click="saveSlot">
          保存
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.block {
  margin-bottom: 20px;
}

.head {
  margin-bottom: 10px;
}

h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.empty {
  padding: 16px 0;
}

.slot {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  margin-top: 8px;
}

.slot.active {
  border-color: color-mix(in srgb, var(--ok) 55%, var(--border));
  box-shadow: inset 3px 0 0 var(--ok);
}

.slot-head {
  gap: 10px;
  margin-bottom: 8px;
}

.slot-name {
  font-weight: 500;
}

.slot-body {
  align-items: flex-start;
}

.slot-form :deep(.n-form-item) {
  margin-bottom: 12px;
}

.hint {
  margin: -4px 0 12px;
}
</style>
