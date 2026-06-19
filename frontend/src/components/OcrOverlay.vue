<template>
  <div class="space-y-6" v-if="pages.length > 0">
    <div
      v-for="page in pages"
      :key="page.page_number"
      class="relative border border-gray-200 rounded-lg overflow-hidden bg-white mx-auto"
      style="max-width: 800px;"
    >
      <img
        :src="`/api/ocr/${taskId}/layers/${page.page_number}`"
        :alt="`Page ${page.page_number}`"
        class="w-full h-auto block select-none"
        loading="lazy"
      />
      <div class="absolute inset-0">
        <span
          v-for="(word, wi) in page.words"
          :key="wi"
          class="absolute block text-transparent hover:text-gray-800 hover:bg-yellow-300/80 border border-blue-500/10 cursor-pointer transition-all text-xs leading-none"
          :style="{
            left: word.x + 'px',
            top: word.y + 'px',
            width: word.width + 'px',
            height: word.height + 'px',
            fontSize: Math.max(10, word.height * 0.7) + 'px',
          }"
          :title="word.text"
        >
          {{ word.text }}
        </span>
      </div>
    </div>
  </div>
  <div v-else class="text-center py-16 text-gray-400">Loading overlay...</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../services/api'

const props = defineProps<{ taskId: string }>()

const pages = ref<any[]>([])

onMounted(async () => {
  try {
    const data = await api.getOverlay(props.taskId)
    pages.value = data.pages
  } catch {
    pages.value = []
  }
})
</script>
