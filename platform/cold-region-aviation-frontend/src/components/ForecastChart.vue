<template>
  <div class="forecast-chart" role="img" :aria-label="mode === 'consumption' ? '10秒耗电量：仿真后验值、LSTM预测与可用基线对照' : '剩余电荷量：仿真值与10秒后预测对照'">
    <VChart :option="option" autoresize />
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { numeric, orderedRows, verifiedPairs } from '@/utils/telemetry'
use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
const props = defineProps({ rows: { type: Array, default: () => [] }, mode: { type: String, default: 'consumption' }, zero: Boolean, baselines: Boolean })
const option = computed(() => {
  const rows = orderedRows(props.rows)
  const start = numeric(rows[0]?.sourceTimeS) === null ? (rows[0]?.time || 0) : 0
  const pairs = verifiedPairs(rows)
  const isConsumption = props.mode === 'consumption'
  const firstPrediction = rows.find(row => row.prediction?.valid)
  const minTime = isConsumption && firstPrediction ? Math.max(0, (firstPrediction.time - start) / 1000 - 1) : 0
  const observed = isConsumption ? pairs.map(p => [(p.time - start) / 1000, p.actual]) : rows.map(r => [(r.time - start) / 1000, numeric(r.remainingCapacityAh)])
  const predicted = rows.map(row => {
    const p = row.prediction
    const value = p?.valid ? numeric(isConsumption ? p.predicted_consumption_Ah : p.predicted_capacity_Ah) : null
    return [(row.time - start) / 1000 + (isConsumption ? 0 : (numeric(p?.forecast_horizon_s) || 10)), value === null ? null : value * (isConsumption ? 1000 : 1)]
  })
  return {
    animation: false,
    textStyle: { fontFamily: '-apple-system, PingFang SC, sans-serif', color: '#56645f', fontSize: 13 },
    color: ['#3f6c50', '#bb773a', '#707782', '#a69972'],
    grid: { left: 64, right: 28, top: 64, bottom: 58 },
    legend: { top: 6, left: 24, right: 18, itemWidth: 22, itemHeight: 3, textStyle: { color: '#43564e', fontSize: 13 } },
    media: [{ query: { maxWidth: 480 }, option: {
      grid: { top: 102, left: 58, right: 24 }, legend: { left: 16, right: 16, top: 5 }, yAxis: { nameGap: 16 }, xAxis: { splitNumber: 4 }
    } }],
    tooltip: { trigger: 'axis', confine: true, backgroundColor: '#fff', borderColor: '#dde3d4', textStyle: { color: '#263425', fontSize: 12 }, valueFormatter: value => value === null ? '暂无' : Number(value).toFixed(isConsumption ? 3 : 6) + (isConsumption ? ' mAh' : ' Ah') },
    xAxis: { type: 'value', name: isConsumption ? '预测发出时间 · 相对秒' : '目标时间 · 相对秒', nameLocation: 'middle', nameGap: 34, min: minTime, axisLine: { lineStyle: { color: '#dfe3d7' } }, axisTick: { show: false }, splitLine: { show: false } },
    yAxis: { type: 'value', name: isConsumption ? '10秒耗电量 / mAh' : '剩余容量 / Ah', nameGap: 22, scale: !props.zero, min: props.zero ? 0 : undefined, splitNumber: 4, axisLabel: { formatter: value => Number(value).toFixed(isConsumption ? 1 : 3) }, splitLine: { lineStyle: { color: '#edf0e7', type: 'dashed' } } },
    series: [
      { name: isConsumption ? '实际耗电（仿真）' : '实际电荷（仿真）', type: 'line', data: observed, smooth: false, connectNulls: false, showSymbol: observed.length < 3, symbolSize: 5, lineStyle: { width: 2.5 } },
      { name: 'LSTM预测', type: 'line', data: predicted, smooth: false, connectNulls: false, showSymbol: false, lineStyle: { width: 2, type: 'dashed' } },
      ...(isConsumption && props.baselines ? [['history_10s','历史耗电延续'],['mean_current_20s','20秒均流估算']].map(([key,name]) => ({
        name, type: 'line', smooth: false, connectNulls: false, showSymbol: false, lineStyle: { width: 1.5, type: 'dotted' },
        data: rows.map(row => { const value=numeric(row.prediction?.baselines?.[key]); return [(row.time-start)/1000,value===null?null:value*1000] })
      })) : [])
    ]
  }
})
</script>
<style scoped>.forecast-chart{height:360px;width:100%}@media(max-width:760px){.forecast-chart{height:350px}}</style>
