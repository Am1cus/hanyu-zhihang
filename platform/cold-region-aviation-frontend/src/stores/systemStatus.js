import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getDashboardOverview } from '@/api/warning'

export const useSystemStatusStore = defineStore('systemStatus', () => {
  const overview = ref({})
  const lastUpdatedAt = ref(null)
  const loading = ref(false)
  const backendOnline = ref(false)

  let pollTimer = null
  let inFlight = null

  const aiStatus = computed(() => {
    const detail = overview.value.aiStatus || {}
    return {
      online: Boolean(detail.online ?? overview.value.aiServiceOnline),
      capacityModelLoaded: Boolean(detail.capacityModelLoaded),
      capacityModelVersion: detail.capacityModelVersion || null,
      airsimCapacityModelAvailable: Boolean(detail.airsimCapacityModelAvailable),
      airsimCapacityModelVersion: detail.airsimCapacityModelVersion || 'airsim_capacity_lstm_v2',
      airsimCapacityTestMapePct: Number(detail.airsimCapacityTestMapePct),
      airsimCapacityForecastHorizonS: Number(detail.airsimCapacityForecastHorizonS || 10),
      flightTimeModelAvailable: Boolean(detail.flightTimeModelAvailable),
      flightTimeModelVersion: detail.flightTimeModelVersion || 'flight_time_lstm_v2',
      quantizationEngine: detail.quantizationEngine || null
    }
  })

  const unhandledCount = computed(() => Number(overview.value.unhandledWarnings || 0))

  async function refresh() {
    if (inFlight) return inFlight

    loading.value = true
    inFlight = getDashboardOverview({ silent: true })
      .then(response => {
        backendOnline.value = true
        overview.value = response.data || {}
        lastUpdatedAt.value = new Date()
        return true
      })
      .catch(error => {
        backendOnline.value = false
        overview.value = {
          ...overview.value,
          aiServiceOnline: false,
          aiStatus: {
            ...(overview.value.aiStatus || {}),
            online: false,
            capacityModelLoaded: false,
            airsimCapacityModelAvailable: false,
            flightTimeModelAvailable: false,
            reason: 'backend_unavailable'
          }
        }
        console.warn('[系统状态] 看板概览刷新失败:', error.message)
        return false
      })
      .finally(() => {
        loading.value = false
        inFlight = null
      })

    return inFlight
  }

  function startPolling(intervalMs = 2000) {
    if (pollTimer) return
    refresh()
    pollTimer = window.setInterval(refresh, intervalMs)
  }

  function stopPolling() {
    if (!pollTimer) return
    window.clearInterval(pollTimer)
    pollTimer = null
  }

  return {
    overview,
    backendOnline,
    lastUpdatedAt,
    loading,
    aiStatus,
    unhandledCount,
    refresh,
    startPolling,
    stopPolling
  }
})
