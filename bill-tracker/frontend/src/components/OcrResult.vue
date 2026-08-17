<template>
  <div class="space-y-6">
    <div v-if="errorCount > 0" class="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3">
      Partial Processing Notice: {{ errorCount }} page{{ errorCount > 1 ? 's' : '' }} had errors.
      Text may be incomplete.
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <h3 class="text-sm font-medium text-gray-500 mb-2">Devanagari (OCR)</h3>
        <pre class="whitespace-pre-wrap text-sm bg-white border rounded-lg p-4 min-h-[200px] max-h-[600px] overflow-y-auto font-[system-ui] leading-relaxed">{{ state.result }}</pre>
      </div>
      <div v-if="state.translation && state.translation !== 'done'">
        <h3 class="text-sm font-medium text-gray-500 mb-2">English (Translation)</h3>
        <div class="text-sm bg-white border rounded-lg p-4 min-h-[200px] max-h-[600px] overflow-y-auto leading-relaxed">{{ state.translation }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskState } from '../services/api'

const props = defineProps<{ taskId: string; state: TaskState }>()

const errorCount = computed(() => Object.keys(props.state.page_errors ?? {}).length)
</script>
