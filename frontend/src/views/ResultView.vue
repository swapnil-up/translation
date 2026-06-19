<template>
  <div>
    <OcrProgress
      v-if="state && (state.status === 'pending' || state.status === 'processing')"
      :state="state"
    />
    <OcrResult
      v-else-if="state && state.status === 'done'"
      :task-id="taskId"
      :state="state"
    />
    <div v-else-if="state && state.status === 'error'" class="text-center py-16">
      <p class="text-red-600 font-medium">Processing failed</p>
      <p class="text-sm text-gray-500 mt-1">{{ state.error }}</p>
    </div>
    <div v-else class="text-center py-16 text-gray-400">
      Loading...
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, type TaskState } from '../services/api'
import OcrProgress from '../components/OcrProgress.vue'
import OcrResult from '../components/OcrResult.vue'

const props = defineProps<{ taskId: string }>()

const state = ref<TaskState | null>(null)
let interval: ReturnType<typeof setInterval> | null = null

async function poll() {
  try {
    state.value = await api.getTaskState(props.taskId)
    if (state.value.status === 'done' || state.value.status === 'error') {
      if (interval) clearInterval(interval)
    }
  } catch {
    if (interval) clearInterval(interval)
  }
}

onMounted(() => {
  poll()
  interval = setInterval(poll, 1500)
})

onUnmounted(() => {
  if (interval) clearInterval(interval)
})
</script>
