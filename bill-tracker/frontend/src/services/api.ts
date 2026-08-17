const BASE = '/api'

export interface TaskState {
  status: 'pending' | 'processing' | 'done' | 'error'
  phase: string
  current: number
  total: number
  queue_position?: number | null
  pages?: any[]
  page_errors?: Record<number, string>
  result?: string | null
  translation?: string | null
  translation_error?: string | null
  error?: string | null
}

export interface ConfigStatus {
  ocr_enabled: boolean
  translation_enabled: boolean
}

export const api = {
  async getConfigStatus(): Promise<ConfigStatus> {
    const res = await fetch(`${BASE}/config/status`)
    if (!res.ok) throw new Error('Failed to fetch config')
    return res.json()
  },

  async uploadPdf(file: File): Promise<{ task_id: string; status: string }> {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/ocr`, { method: 'POST', body: fd })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Upload failed (${res.status})`)
    }
    return res.json()
  },

  async getTaskState(taskId: string): Promise<TaskState> {
    const res = await fetch(`${BASE}/ocr/${taskId}`)
    if (!res.ok) throw new Error('Task not found')
    return res.json()
  },

  async triggerTranslation(taskId: string): Promise<void> {
    const res = await fetch(`${BASE}/ocr/${taskId}/translate`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Translation failed')
    }
  },

  async getOverlay(taskId: string): Promise<{ pages: any[] }> {
    const res = await fetch(`${BASE}/ocr/${taskId}/overlay`)
    if (!res.ok) throw new Error('Overlay not available')
    return res.json()
  },

  async deleteTask(taskId: string): Promise<void> {
    await fetch(`${BASE}/ocr/${taskId}`, { method: 'DELETE' })
  }
}
