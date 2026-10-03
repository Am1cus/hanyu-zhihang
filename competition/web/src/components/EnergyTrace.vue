<script setup>
import { computed } from 'vue'
const props = defineProps({ telemetry: { type: Array, default: () => [] } })
const records = computed(() => props.telemetry.filter((item) => Number.isFinite(item.t_s) && Number.isFinite(item.discharged_wh)))
const last = computed(() => records.value.at(-1))
const maximum = computed(() => Math.max(...records.value.map((item) => item.discharged_wh), 1))
const path = computed(() => {
  if (records.value.length < 2) return ''
  const begin = records.value[0].t_s
  const range = Math.max(last.value.t_s - begin, 1)
  return records.value.map((item) => `${30 + (item.t_s - begin) / range * 540},${130 - item.discharged_wh / maximum.value * 100}`).join(' ')
})
</script>
<template>
  <div class="trace-chart">
    <div class="section-heading"><h3>累计仿真耗能</h3><span>{{ last?.discharged_wh?.toFixed(2) || '—' }} Wh</span></div>
    <svg v-if="records.length > 1" viewBox="0 0 600 160" role="img" aria-label="累计仿真耗能随时间变化">
      <path d="M30 20V130H570" fill="none" stroke="#d4ded6" />
      <path d="M30 80H570M30 30H570" fill="none" stroke="#edf1ed" />
      <polyline :points="path" fill="none" stroke="#3e785d" stroke-width="2.5" />
      <text x="30" y="150" font-size="11" fill="#6c776f">{{ records[0]?.t_s?.toFixed(0) }} s</text><text x="540" y="150" font-size="11" fill="#6c776f">{{ last?.t_s?.toFixed(0) }} s</text>
      <text x="5" y="30" font-size="10" fill="#6c776f">{{ maximum.toFixed(1) }}</text>
    </svg>
    <p v-else class="empty-inline">接收到至少两条后端遥测后显示曲线。</p>
    <p class="helper">按后端电压、电流与仿真时间累计；运行视图最多显示最近 300 条，完整记录见档案。</p>
  </div>
</template>
