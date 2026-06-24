<template>
  <div>
    <!-- Waking up (cold start) -->
    <div v-if="waking" class="text-center space-y-4 py-16">
      <div class="animate-pulse flex justify-center">
        <svg class="w-10 h-10 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p class="text-orange-600 font-medium">Space is waking up...</p>
      <p class="text-sm text-gray-400">This takes 30–60 seconds after inactivity.</p>
      <p v-if="retryCount > 2" class="text-xs text-gray-400">Retrying ({{ retryCount }}s)...</p>
    </div>

    <!-- Progress -->
    <OcrProgress
      v-else-if="state && (state.status === 'pending' || state.status === 'processing')"
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
          .txt
        </button>

        <button
          @click="downloadCsv"
          class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          .csv
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
      <p class="text-red-600 font-medium">
        {{ state.phase === 'expired' ? 'Task expired' : 'Processing failed' }}
      </p>
      <p class="text-sm text-gray-500 mt-1">{{ state.error }}</p>
      <router-link to="/" class="inline-block mt-4 text-sm text-blue-600 underline">
        Upload another PDF
      </router-link>
    </div>

    <!-- Initial loading -->
    <div v-else class="text-center py-16 text-gray-400">
      <div class="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-3" />
      Loading...
    </div>
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
const waking = ref(false)
const retryCount = ref(0)
let interval: ReturnType<typeof setInterval> | null = null
let failCount = 0

const { configStatus } = useOcr()
const translationEnabled = computed(() => configStatus.value?.translation_enabled ?? false)

const errorCount = computed(() => Object.keys(state.value?.page_errors ?? {}).length)

async function poll() {
  try {
    state.value = await api.getTaskState(props.taskId)
    failCount = 0
    retryCount.value = 0
    waking.value = false
    if (state.value.status === 'done' || state.value.status === 'error') {
      if (interval) clearInterval(interval)
    }
  } catch (err: any) {
    failCount++
    retryCount.value = Math.round(failCount * 1.5)
    if (err.message?.includes('Task not found')) {
      if (interval) clearInterval(interval)
      state.value = { status: 'error', phase: 'expired', current: 0, total: 0, error: 'This task has expired or was not found.' }
      return
    }
    if (failCount >= 2) {
      waking.value = true
    }
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

function downloadCsv() {
  const text = state.value?.result ?? ''
  const lines = text.split('\n').filter(Boolean)
  const rows = lines.map(l => {
    const escaped = l.replace(/"/g, '""')
    return `"${escaped}"`
  })
  const csv = 'text\n' + rows.join('\n')
  const bom = '\uFEFF'
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'ocr-result.csv'; a.click()
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
