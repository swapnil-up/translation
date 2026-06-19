<template>
  <div class="space-y-8" v-if="pages.length > 0">
    <div
      v-for="page in pages"
      :key="page.page_number"
      class="relative border border-gray-200 rounded-lg overflow-hidden bg-white mx-auto"
      style="max-width: 800px;"
    >
      <img
        :src="`/api/ocr/${taskId}/layers/${page.page_number}`"
        :alt="`Page ${page.page_number}`"
        class="w-full h-auto block"
        loading="lazy"
        @load="onImgLoad($event, page.page_number)"
      />
      <div
        v-if="pageSizes[page.page_number]"
        class="absolute inset-0 pointer-events-none"
        :style="{
          width: pageSizes[page.page_number].w + 'px',
          height: pageSizes[page.page_number].h + 'px',
        }"
      >
        <div
          v-for="(block, bi) in page.blocks"
          :key="bi"
          class="absolute"
          :style="{
            left: (block.x * pageSizes[page.page_number].sx) + 'px',
            top: (block.y * pageSizes[page.page_number].sy) + 'px',
            width: (block.width * pageSizes[page.page_number].sx) + 'px',
          }"
        >
          <div v-for="(line, li) in block.lines" :key="li">
            <div
              class="text-[11px] leading-tight break-words px-0.5 rounded-sm"
              :class="line.translation ? 'bg-black/40 text-yellow-200' : 'bg-black/30 text-cyan-300'"
            >
              {{ line.text }}
            </div>
            <div
              v-if="line.translation"
              class="text-[10px] leading-tight break-words px-0.5 rounded-sm bg-black/30 text-orange-200"
            >
              {{ line.translation }}
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

const pages = ref<any[]>([])
const pageSizes = reactive<Record<number, PageSize>>({})

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
