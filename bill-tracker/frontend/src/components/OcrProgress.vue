<template>
  <div class="max-w-lg mx-auto text-center space-y-6 py-16">
    <div class="flex items-center justify-center gap-3">
      <div class="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full" />
      <div class="text-sm font-medium text-gray-700">
        <template v-if="state.status === 'pending'">Queued — Position {{ state.queue_position ?? '?' }}</template>
        <template v-else>{{ phaseLabel }}</template>
      </div>
    </div>

    <div v-if="state.status === 'processing'" class="space-y-3">
      <div class="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
        <div
          class="bg-blue-600 h-full rounded-full transition-all duration-300 ease-out"
          :style="{ width: percent + '%' }"
        />
      </div>
      <div class="flex justify-between text-xs text-gray-400">
        <span>{{ state.current }} of {{ state.total }} pages</span>
        <span>{{ elapsed }}</span>
      </div>
    </div>

    <div v-if="state.status === 'pending'" class="flex justify-center">
      <div class="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { TaskState } from '../services/api'

const props = defineProps<{ state: TaskState }>()
const startTime = Date.now()
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

const phaseLabel = computed(() => {
  const m: Record<string, string> = {
    queued: 'Waiting in queue...',
    converting_pdf: 'Rendering document pages...',
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

const elapsed = computed(() => {
  const sec = Math.floor((now.value - startTime) / 1000)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
})

onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
