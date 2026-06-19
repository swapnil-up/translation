<template>
  <div class="space-y-6">
    <!-- Warning banner for partial errors -->
    <div
      v-if="errorCount > 0"
      class="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3"
    >
      Partial Processing Notice: {{ errorCount }} page{{ errorCount > 1 ? 's' : '' }} had errors.
      Text may be incomplete.
    </div>

    <!-- Action bar -->
    <div class="flex flex-wrap items-center gap-3">
      <button
        @click="downloadTxt"
        class="text-sm px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        Download .txt
      </button>
      <button
        @click="copyText"
        class="text-sm px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        {{ copied ? 'Copied!' : 'Copy to Clipboard' }}
      </button>
      <button
        @click="handleTranslate"
        :disabled="!translationEnabled"
        class="text-sm px-4 py-2 rounded-lg transition-colors"
        :class="translationEnabled
          ? 'bg-blue-600 text-white hover:bg-blue-700'
          : 'bg-gray-200 text-gray-400 cursor-not-allowed'"
        :title="translationEnabled ? '' : 'Translation disabled — no API key configured'"
      >
        {{ translating ? 'Translating...' : 'Translate to English' }}
      </button>
    </div>

    <!-- Text panels -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <h3 class="text-sm font-medium text-gray-500 mb-2">Devanagari (OCR)</h3>
        <pre class="whitespace-pre-wrap text-sm bg-white border rounded-lg p-4 min-h-[200px] max-h-[600px] overflow-y-auto font-[system-ui] leading-relaxed">{{ state.result }}</pre>
      </div>
      <div v-if="state.translation">
        <h3 class="text-sm font-medium text-gray-500 mb-2">English (Translation)</h3>
        <div class="text-sm bg-white border rounded-lg p-4 min-h-[200px] max-h-[600px] overflow-y-auto leading-relaxed">{{ state.translation }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type TaskState } from '../services/api'
import { useOcr } from '../composables/useOcr'

const props = defineProps<{ taskId: string; state: TaskState }>()

const { configStatus } = useOcr()
const copied = ref(false)
const translating = ref(false)
const translationEnabled = computed(() => configStatus.value?.translation_enabled ?? false)

const errorCount = computed(() => Object.keys(props.state.page_errors ?? {}).length)

function downloadTxt() {
  const blob = new Blob([props.state.result ?? ''], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'ocr-result.txt'; a.click()
  URL.revokeObjectURL(url)
}

async function copyText() {
  if (!props.state.result) return
  await navigator.clipboard.writeText(props.state.result)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function handleTranslate() {
  if (translating.value || !translationEnabled.value) return
  translating.value = true
  try {
    await api.triggerTranslation(props.taskId)
    // Start polling for translation result
    const iv = setInterval(async () => {
      const s = await api.getTaskState(props.taskId)
      if (s.translation || s.translation_error) {
        clearInterval(iv)
        translating.value = false
        Object.assign(props.state, s)
      }
    }, 1000)
  } catch {
    translating.value = false
  }
}

onMounted(async () => {
  try {
    const cs = await api.getConfigStatus()
    useOcr().setConfigStatus(cs)
  } catch {}
})
</script>
