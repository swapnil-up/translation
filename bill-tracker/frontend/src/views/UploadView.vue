<template>
  <div class="space-y-6">
    <div class="text-center space-y-2">
      <h2 class="text-2xl font-semibold">Extract Devanagari Text from PDF</h2>
      <p class="text-gray-500 text-sm">
        Upload a Nepali government PDF to extract text via OCR
      </p>
    </div>
    <FileUpload @file-ready="handleFile" />
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import FileUpload from '../components/FileUpload.vue'
import { api } from '../services/api'

const router = useRouter()

async function handleFile(file: File) {
  try {
    const { task_id } = await api.uploadPdf(file)
    router.push({ name: 'result', params: { taskId: task_id } })
  } catch (err: any) {
    alert(err.message)
  }
}
</script>
