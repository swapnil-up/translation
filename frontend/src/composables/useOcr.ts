import { ref, readonly } from 'vue'
import type { TaskState, ConfigStatus } from '../services/api'

const currentTaskId = ref<string | null>(null)
const taskState = ref<TaskState | null>(null)
const configStatus = ref<ConfigStatus | null>(null)

export function useOcr() {
  function setTaskId(id: string | null) { currentTaskId.value = id }
  function setTaskState(state: TaskState | null) { taskState.value = state }
  function setConfigStatus(cs: ConfigStatus) { configStatus.value = cs }

  return {
    currentTaskId: readonly(currentTaskId),
    taskState: readonly(taskState),
    configStatus: readonly(configStatus),
    setTaskId,
    setTaskState,
    setConfigStatus,
  }
}
