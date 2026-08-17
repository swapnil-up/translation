<template>
  <div class="space-y-8" v-if="pages.length > 0">
    <div
      v-for="page in pages"
      :key="page.page_number"
      class="relative border border-gray-200 rounded-lg bg-white mx-auto"
      style="max-width: 800px;"
    >
      <div class="overflow-hidden rounded-lg">
      <img
        :src="`/api/ocr/${taskId}/layers/${page.page_number}`"
        :alt="`Page ${page.page_number}`"
        class="w-full h-auto block"
        loading="lazy"
        @load="onImgLoad($event, page.page_number)"
      />
      </div>
      <div
        v-if="pageSizes[page.page_number]"
        class="absolute inset-0 pointer-events-none"
        :style="{
          width: pageSizes[page.page_number].w + 'px',
          height: pageSizes[page.page_number].h + 'px',
        }"
      >
        <div
          v-for="line in flatLines(page)"
          :key="`${page.page_number}-${line.li}`"
          class="absolute overflow-hidden rounded-sm group pointer-events-auto ocr-block"
          :class="line.translation ? 'bg-black/40' : 'bg-black/30'"
          :style="{
            left: (line.x * pageSizes[page.page_number].sx) + 'px',
            top: (line.y * pageSizes[page.page_number].sy) + 'px',
            width: Math.max(line.width * pageSizes[page.page_number].sx, 20) + 'px',
            height: (line.height * pageSizes[page.page_number].sy) + 'px',
          }"
        >
          <div class="relative">
            <div class="hidden group-hover:block text-[11px] leading-tight mb-1 whitespace-nowrap overflow-hidden text-ellipsis opacity-60" style="color: #88ddff;">{{ line.text }}</div>
            <div class="text-[11px] leading-tight break-words px-0.5 group-hover:text-2xl group-hover:leading-snug transition-all duration-150">
              <span style="color: #00eeff;">{{ line.text }}</span>
              <span v-if="line.translation" class="block text-[10px] group-hover:text-lg" style="color: #ff6600;">{{ line.translation }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="text-center py-16 text-gray-400">Loading overlay...</div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { api } from '../services/api'

const props = defineProps<{ taskId: string }>()

interface PageSize {
  w: number
  h: number
  sx: number
  sy: number
}

interface FlatLine {
  li: number
  text: string
  translation: string
  x: number
  y: number
  width: number
  height: number
}

const pages = ref<any[]>([])
const pageSizes = reactive<Record<number, PageSize>>({})

function flatLines(page: any): FlatLine[] {
  const lines: FlatLine[] = []
  let li = 0
  for (const block of page.blocks) {
    for (const line of block.lines) {
      lines.push({
        li: li++,
        text: line.text,
        translation: line.translation || '',
        x: line.x,
        y: line.y,
        width: line.width,
        height: line.height,
      })
    }
  }
  return lines
}

function onImgLoad(e: Event, pageNum: number) {
  const img = e.target as HTMLImageElement
  const nw = img.naturalWidth
  const nh = img.naturalHeight
  const rw = img.clientWidth
  const rh = img.clientHeight
  if (nw && nh) {
    pageSizes[pageNum] = {
      w: rw,
      h: rh,
      sx: rw / nw,
      sy: rh / nh,
    }
  }
}

onMounted(async () => {
  try {
    const data = await api.getOverlay(props.taskId)
    pages.value = data.pages
  } catch {
    pages.value = []
  }
})
</script>

<style scoped>
.ocr-block:hover {
  width: auto !important;
  min-width: 250px !important;
  max-width: 500px !important;
  height: auto !important;
  z-index: 100 !important;
  overflow: visible !important;
}
</style>
