<template>
  <div>
    <!-- Progress -->
    <OcrProgress
      v-if="state && (state.status === 'pending' || state.status === 'processing')"
      :state="state"
    />

    <!-- Result -->
    <template v-else-if="state && state.status === 'done'">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <button
          @click="viewMode = viewMode === 'overlay' ? 'text' : 'overlay'"
          class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          {{ viewMode === 'overlay' ? 'Text View' : 'Overlay View' }}
        </button>

        <button
          @click="downloadTxt"
          class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Download .txt
        </button>

        <button
          @click="copyText"
          class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>

        <button
          @click="handleTranslate"
          :disabled="!translationEnabled"
          class="text-sm px-3 py-1.5 rounded-lg"
          :class="translationEnabled
            ? 'bg-blue-600 text-white hover:bg-blue-700'
            : 'bg-gray-200 text-gray-400 cursor-not-allowed'"
          :title="translationEnabled ? '' : 'No API key configured'"
        >
          {{ translating ? 'Translating...' : 'Translate' }}
        </button>
      </div>

      <div v-if="errorCount > 0" class="mb-4 bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3">
        {{ errorCount }} page{{ errorCount > 1 ? 's' : '' }} had errors — text may be incomplete.
      </div>

      <OcrOverlay v-if="viewMode === 'overlay'" :task-id="taskId" :key="overlayKey" />
      <OcrResult v-else :task-id="taskId" :state="state" />
    </template>

    <!-- Error -->
    <div v-else-if="state && state.status === 'error'" class="text-center py-16">
      <p class="text-red-600 font-medium">Processing failed</p>
      <p class="text-sm text-gray-500 mt-1">{{ state.error }}</p>
    </div>

    <!-- Loading -->
    <div v-else class="text-center py-16 text-gray-400">Loading...</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, type TaskState } from '../services/api'
import { useOcr } from '../composables/useOcr'
import OcrProgress from '../components/OcrProgress.vue'
import OcrResult from '../components/OcrResult.vue'
import OcrOverlay from '../components/OcrOverlay.vue'

const props = defineProps<{ taskId: string }>()

const state = ref<TaskState | null>(null)
const viewMode = ref<'overlay' | 'text'>('overlay')
const copied = ref(false)
const translating = ref(false)
const overlayKey = ref(0)
let interval: ReturnType<typeof setInterval> | null = null

const { configStatus } = useOcr()
const translationEnabled = computed(() => configStatus.value?.translation_enabled ?? false)

const errorCount = computed(() => Object.keys(state.value?.page_errors ?? {}).length)

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

function downloadTxt() {
  const text = state.value?.result ?? ''
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'ocr-result.txt'; a.click()
  URL.revokeObjectURL(url)
}

async function copyText() {
  const text = state.value?.result ?? ''
  if (!text) return
  await navigator.clipboard.writeText(text)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function handleTranslate() {
  if (translating.value || !translationEnabled.value) return
  translating.value = true
  try {
    await api.triggerTranslation(props.taskId)
    const iv = setInterval(async () => {
      const s = await api.getTaskState(props.taskId)
      if (s.translation || s.translation_error) {
        clearInterval(iv)
        translating.value = false
        overlayKey.value++
      }
    }, 1000)
  } catch {
    translating.value = false
  }
}

onMounted(async () => {
  poll()
  interval = setInterval(poll, 1500)
  try {
    const cs = await api.getConfigStatus()
    useOcr().setConfigStatus(cs)
  } catch {}
})

onUnmounted(() => {
  if (interval) clearInterval(interval)
})
</script>
