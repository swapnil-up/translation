<template>
  <div class="max-w-lg mx-auto text-center space-y-6 py-16">
    <div class="text-sm font-medium text-gray-700">
      <template v-if="state.status === 'pending'">Queued — Position {{ state.queue_position ?? '?' }}</template>
      <template v-else>{{ phaseLabel }}</template>
    </div>

    <div v-if="state.status === 'processing'" class="space-y-2">
      <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
        <div
          class="bg-blue-600 h-full rounded-full transition-all duration-300 ease-out"
          :style="{ width: percent + '%' }"
        />
      </div>
      <p class="text-xs text-gray-400">{{ state.current }} of {{ state.total }} pages</p>
    </div>

    <div v-if="state.status === 'pending'" class="flex justify-center">
      <div class="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskState } from '../services/api'

const props = defineProps<{ state: TaskState }>()

const phaseLabel = computed(() => {
  const m: Record<string, string> = {
    queued: 'Waiting in queue...',
    converting_pdf: 'Converting document pages...',
    ocr: 'Reading Devanagari text...',
    translating: 'Translating to English...',
    completed: 'Done!',
  }
  return m[props.state.phase] ?? 'Processing...'
})

const percent = computed(() => {
  if (props.state.total === 0) return 0
  return Math.round((props.state.current / props.state.total) * 100)
})
</script>
