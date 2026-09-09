import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { orderedRows, timestamp } from '@/utils/telemetry'
import { getRun, getRunEvents } from '@/api/runs'

export const useTelemetryStore = defineStore('telemetry', () => {
  const historyData = ref(new Map()) // runId -> rows, never mix flights by droneId
  const selectedRunId = ref(null), liveRunId = ref(null), followLive = ref(true)
  const runDetail = ref(null), loadingArchive = ref(false), archiveError = ref('')
  const connected = ref(false), lastMessageAt = ref(null)
  const rows = computed(() => historyData.value.get(selectedRunId.value) || [])
  const receivedCount = computed(() => rows.value.length)
  const realtimeData = computed(() => new Map([...historyData.value.values()].filter(x => x.length).map(x => [x.at(-1).droneId, x.at(-1)])))
  let ws, reconnectTimer, stopped = false, loadId = 0

  function ingest(message, live = true) {
    const data = message.telemetry
    const id = data?.runId || message.runId
    if (!id || data?.droneId == null) return
    const receivedAt = live ? Date.now() : timestamp(message.serverTime)
    const history = orderedRows([...(historyData.value.get(id) || []), { ...data, prediction: message.prediction || null, verification: message.verification, receivedAt }]).slice(-1800)
    historyData.value = new Map(historyData.value).set(id, history)
    liveRunId.value = id
    if (followLive.value) selectedRunId.value = id
    lastMessageAt.value = receivedAt
    // Keep only selected/live plus one recent run in browser memory; the database is the archive.
    while (historyData.value.size > 3) {
      const discard = [...historyData.value.keys()].find(key => key !== id && key !== selectedRunId.value)
      if (!discard) break
      historyData.value.delete(discard)
    }
  }

  async function refreshDetail() {
    const id = selectedRunId.value
    if (!id) { runDetail.value = null; return }
    try {
      const response = await getRun(id)
      if (selectedRunId.value === id) { runDetail.value = response.data; archiveError.value = '' }
    } catch {
      if (selectedRunId.value === id) archiveError.value = '无法读取实验档案，请确认新版后台已启动。'
    }
  }

  async function openRun(id) {
    const version = ++loadId
    followLive.value = false
    selectedRunId.value = id
    runDetail.value = null
    loadingArchive.value = true
    archiveError.value = ''
    try {
      const detail = await getRun(id)
      let after = Math.max(-1, (detail.data.metrics?.last_sample_seq ?? detail.data.sampleCount - 1) - 1800)
      let events = []
      for (let page = 0; page < 2; page++) {
        const response = await getRunEvents(id, after, page === 0 ? 1000 : 800)
        if (version !== loadId) return
        const chunk = response.data || []
        events.push(...chunk)
        if (chunk.length < (page === 0 ? 1000 : 800)) break
        after = chunk.at(-1).telemetry.sampleSeq
      }
      if (version !== loadId) return
      const archived = events.map(event => ({ ...event.telemetry, prediction: event.prediction, verification: event.verification, receivedAt: timestamp(event.serverTime) }))
      // Reconcile live events that arrived during the HTTP request instead of dropping them.
      historyData.value = new Map(historyData.value).set(id, orderedRows([...(historyData.value.get(id) || []), ...archived]).slice(-1800))
      runDetail.value = detail.data
    } catch {
      if (version === loadId) archiveError.value = '历史记录加载失败。档案可能不存在，或后台暂不可用。'
    } finally { if (version === loadId) loadingArchive.value = false }
  }

  function resumeLive() {
    ++loadId
    loadingArchive.value = false
    followLive.value = true
    selectedRunId.value = liveRunId.value
    refreshDetail()
  }

  function resetDisplay(id = null) {
    liveRunId.value = id
    if (followLive.value) { selectedRunId.value = id; runDetail.value = null; lastMessageAt.value = null }
  }

  function connect() {
    if (ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(ws.readyState)) return
    stopped = false
    clearTimeout(reconnectTimer)
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/telemetry`)
    ws = socket
    socket.onopen = () => { connected.value = true }
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'demo-reset') return resetDisplay()
        if (message.type === 'run-started') return resetDisplay(message.runId)
        if (message.type === 'run-finished') { refreshDetail(); return }
        if (message.type === 'snapshot') {
          for (const item of message.events || []) ingest(item, false)
          refreshDetail()
          return
        }
        ingest(message)
      } catch (error) { console.warn('[遥测] 无法解析消息', error) }
    }
    socket.onclose = () => {
      if (ws !== socket) return
      connected.value = false
      ws = null
      if (!stopped) reconnectTimer = setTimeout(connect, 3000)
    }
    socket.onerror = () => { connected.value = false }
  }
  function disconnect() {
    stopped = true
    clearTimeout(reconnectTimer)
    const socket = ws
    ws = null
    connected.value = false
    socket?.close()
  }
  const getDroneData = id => realtimeData.value.get(id) || null
  return { rows, historyData, realtimeData, receivedCount, lastMessageAt, connected, selectedRunId, liveRunId, followLive, runDetail, archiveError, loadingArchive, connect, disconnect, getDroneData, openRun, resumeLive, refreshDetail }
})
