<script setup lang="ts">
import { computed } from 'vue'
import type { IpView } from '@/api'
import { countryName } from '@/utils/countries'
import RegionFlag from './RegionFlag.vue'
import StatusDot from './StatusDot.vue'

// 所有出现 IP 的地方都用这个组件：国旗 · IP · 名称/备注 · 状态
const props = withDefaults(
  defineProps<{
    item: IpView
    rank?: number | null
    showStatus?: boolean
    showOrg?: boolean
    showLabel?: boolean
    compact?: boolean
  }>(),
  { rank: null, showStatus: true, showOrg: false, showLabel: true, compact: false },
)

const tooltip = computed(() => {
  const g = props.item.geo
  const parts = [props.item.ip]
  if (g?.private) parts.push('内网 / 保留地址')
  else if (g?.country) parts.push(countryName(g.country))
  if (g?.org) parts.push(`AS${g.asn ?? ''} ${g.org}`.trim())
  if (props.item.name) parts.push(`名称：${props.item.name}`)
  if (props.item.note) parts.push(`备注：${props.item.note}`)
  return parts.join('\n')
})

const label = computed(() => props.item.name || props.item.note)
</script>

<template>
  <span class="ip-badge" :class="{ compact, lead: rank === 1 }" :title="tooltip">
    <span v-if="rank" class="rank num">{{ rank }}</span>
    <RegionFlag :code="item.geo?.country" :size="compact ? 11 : 12" />
    <span class="ip mono">{{ item.ip }}</span>
    <span v-if="label && showLabel && !compact" class="label">{{ label }}</span>
    <span v-if="showOrg && item.geo?.org" class="org">{{ item.geo.org }}</span>
    <StatusDot v-if="showStatus && item.probe" :status="item.probe.status" />
  </span>
</template>

<style scoped>
.ip-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  max-width: 100%;
  white-space: nowrap;
}

.ip-badge.compact {
  height: 22px;
  padding: 0 6px;
  gap: 5px;
}

.ip-badge.lead {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: var(--accent-soft);
}

.rank {
  min-width: 14px;
  font-size: 11px;
  color: var(--text-3);
  text-align: center;
}

.lead .rank {
  color: var(--accent);
  font-weight: 600;
}

.ip {
  font-size: 12.5px;
}

.label {
  color: var(--text-2);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.org {
  color: var(--text-3);
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
</style>
