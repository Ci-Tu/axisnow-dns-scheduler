<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  dateZhCN,
  zhCN,
} from 'naive-ui'
import AppShell from '@/components/layout/AppShell.vue'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const { naiveTheme, overrides } = useTheme()
const bare = computed(() => route.meta.public === true)
</script>

<template>
  <NConfigProvider
    :theme="naiveTheme"
    :theme-overrides="overrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
    abstract
  >
    <NMessageProvider placement="top" :max="3">
      <NDialogProvider>
        <RouterView v-if="bare" />
        <AppShell v-else>
          <RouterView :key="route.path" />
        </AppShell>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
