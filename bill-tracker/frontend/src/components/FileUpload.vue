<template>
  <div
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
    @click="clickInput()"
    :class="[
      'border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer',
      isDragging
        ? 'border-blue-500 bg-blue-50/50 scale-[1.01]'
        : 'border-gray-300 hover:border-gray-400 bg-gray-50'
    ]"
  >
    <input
      type="file"
      ref="fileInput"
      class="hidden"
      accept="application/pdf"
      @change="handleSelect"
    />
    <div class="space-y-3">
      <div class="text-4xl text-gray-400">
        <svg class="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      </div>
      <p class="text-sm text-gray-600">
        <span class="font-semibold text-blue-600">Click to upload</span>
        or drag and drop your PDF here
      </p>
      <p class="text-xs text-gray-400">PDF documents up to 50MB</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const MAX_BYTES = 50 * 1024 * 1024

const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const emit = defineEmits<{ 'file-ready': [file: File] }>()

function clickInput() { fileInput.value?.click() }

function checkFile(file: File) {
  if (file.type !== 'application/pdf') { alert('Only PDF files are accepted.'); return false }
  if (file.size > MAX_BYTES) { alert('File exceeds 50MB limit.'); return false }
  return true
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && checkFile(file)) emit('file-ready', file)
}

function handleSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file && checkFile(file)) emit('file-ready', file)
}
</script>
