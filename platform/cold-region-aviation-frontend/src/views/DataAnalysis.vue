<template>
  <div class="data-analysis fade-in">
    <div class="page-header">
      <h1 class="page-title">数据分析</h1>
      <div style="display: flex; gap: 12px;">
        <el-select v-model="selectedDrone" placeholder="选择无人机" style="width: 200px;">
          <el-option label="UAV-001 寒域一号" value="1" />
          <el-option label="UAV-002 寒域二号" value="2" />
          <el-option label="UAV-003 寒域三号" value="3" />
        </el-select>
        <el-date-picker v-model="dateRange" type="datetimerange" range-separator="至"
          start-placeholder="开始时间" end-placeholder="结束时间" style="width: 380px;" />
        <el-button type="primary" @click="fetchData">查询</el-button>
      </div>
    </div>

    <!-- 温度与电量趋势 -->
    <div class="charts-row">
      <div class="chart-container">
        <h3 class="chart-title">环境温度 vs 电池电量</h3>
        <v-chart :option="tempBatteryChart" autoresize style="height: 320px;" />
      </div>
      <div class="chart-container">
        <h3 class="chart-title">电压与电流变化</h3>
        <v-chart :option="voltageCurrentChart" autoresize style="height: 320px;" />
      </div>
    </div>

    <!-- 风速与衰减 -->
    <div class="charts-row" style="margin-top: 16px;">
      <div class="chart-container">
        <h3 class="chart-title">风速趋势</h3>
        <v-chart :option="windChart" autoresize style="height: 320px;" />
      </div>
      <div class="chart-container">
        <h3 class="chart-title">容量衰减率与温度关系</h3>
        <v-chart :option="decayChart" autoresize style="height: 320px;" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, ScatterChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, LineChart, ScatterChart, TitleComponent, TooltipComponent, GridComponent, LegendComponent])

const selectedDrone = ref('1')
const dateRange = ref(null)
const fetchData = () => {}

const timeLabels = ['10:00', '10:10', '10:20', '10:30', '10:40', '10:50', '11:00', '11:10', '11:20', '11:30']
const axisStyle = { axisLabel: { color: '#c0c4cc' }, axisLine: { lineStyle: { color: '#2a3555' } }, splitLine: { lineStyle: { color: '#2a3555' } } }

const tempBatteryChart = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { textStyle: { color: '#c0c4cc' } },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: timeLabels, ...axisStyle },
  yAxis: [
    { type: 'value', name: '温度(°C)', ...axisStyle },
    { type: 'value', name: '电量(%)', ...axisStyle }
  ],
  series: [
    { name: '环境温度', type: 'line', smooth: true, data: [-18, -19, -21, -23, -25, -26, -27, -26, -25, -24], lineStyle: { color: '#409eff' }, itemStyle: { color: '#409eff' } },
    { name: '电池电量', type: 'line', smooth: true, yAxisIndex: 1, data: [95, 90, 84, 77, 68, 58, 48, 40, 33, 28], lineStyle: { color: '#67c23a' }, itemStyle: { color: '#67c23a' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(103,194,58,0.3)' }, { offset: 1, color: 'rgba(103,194,58,0)' }] } } }
  ]
}))

const voltageCurrentChart = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { textStyle: { color: '#c0c4cc' } },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: timeLabels, ...axisStyle },
  yAxis: [
    { type: 'value', name: '电压(V)', ...axisStyle },
    { type: 'value', name: '电流(A)', ...axisStyle }
  ],
  series: [
    { name: '电压', type: 'line', smooth: true, data: [25.2, 24.8, 24.3, 23.7, 23.0, 22.5, 22.0, 21.6, 21.2, 20.8], lineStyle: { color: '#e6a23c' }, itemStyle: { color: '#e6a23c' } },
    { name: '电流', type: 'line', smooth: true, yAxisIndex: 1, data: [12, 14, 15, 16, 18, 20, 22, 23, 24, 25], lineStyle: { color: '#f56c6c' }, itemStyle: { color: '#f56c6c' } }
  ]
}))

const windChart = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: timeLabels, ...axisStyle },
  yAxis: { type: 'value', name: '风速(m/s)', ...axisStyle },
  series: [{
    name: '风速', type: 'line', smooth: true,
    data: [4, 5, 6, 7, 8, 9, 8, 7, 6, 5],
    lineStyle: { color: '#909399' },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(144,147,153,0.3)' }, { offset: 1, color: 'rgba(144,147,153,0)' }] } },
    markLine: { data: [{ yAxis: 8, name: '安全阈值', lineStyle: { color: '#f56c6c', type: 'dashed' }, label: { color: '#f56c6c' } }] }
  }]
}))

const decayChart = computed(() => ({
  tooltip: { trigger: 'item', formatter: (p) => `温度: ${p.data[0]}°C<br/>衰减率: ${p.data[1]}%` },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'value', name: '温度(°C)', ...axisStyle },
  yAxis: { type: 'value', name: '衰减率(%)', ...axisStyle },
  series: [{
    type: 'scatter', symbolSize: 12,
    itemStyle: { color: '#f56c6c' },
    data: [[-5, 10], [-10, 18], [-15, 28], [-18, 35], [-20, 40], [-22, 44], [-25, 52], [-27, 58], [-30, 65]]
  }]
}))
</script>

<style scoped>
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
</style>
