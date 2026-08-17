<template>
  <div class="min-h-screen flex flex-col">
    <header class="border-b bg-white shadow-sm">
      <div class="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
        <h1 class="text-xl font-bold tracking-tight">Nepali Admin Copilot</h1>
        <span class="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">OCR</span>
      </div>
    </header>
    <main class="flex-1 max-w-5xl mx-auto px-4 py-8 w-full">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>
