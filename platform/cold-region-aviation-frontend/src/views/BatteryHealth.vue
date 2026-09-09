<template>
  <div class="battery-health fade-in">
    <div class="page-header">
      <h1 class="page-title">电池健康评估</h1>
      <el-select v-model="selectedDrone" placeholder="选择无人机" style="width: 200px;">
        <el-option label="UAV-001 寒域一号" value="1" />
        <el-option label="UAV-002 寒域二号" value="2" />
        <el-option label="UAV-003 寒域三号" value="3" />
      </el-select>
    </div>

    <!-- 电池状态概览 -->
    <div class="battery-overview">
      <div class="stat-card" style="text-align: center;">
        <div class="stat-label">健康评分</div>
        <div class="stat-value" :style="{ color: getScoreColor(battery.healthScore) }">
          {{ battery.healthScore || '--' }}
        </div>
        <el-progress type="circle" :percentage="battery.healthScore || 0"
          :color="getScoreColor(battery.healthScore)" :width="100" style="margin-top: 8px;" />
      </div>
      <div class="stat-card">
        <div class="stat-label">当前电量</div>
        <div class="stat-value">{{ battery.currentLevel || '--' }}%</div>
        <el-progress :percentage="battery.currentLevel || 0" :color="getBatteryColor(battery.currentLevel)" />
      </div>
      <div class="stat-card">
        <div class="stat-label">AI预测剩余航程</div>
        <div class="stat-value" style="color: var(--primary);">{{ battery.predictedRange || '--' }} km</div>
        <div class="stat-label" style="margin-top: 8px;">预测飞行时间: {{ battery.predictedFlightTime || '--' }} min</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">容量衰减率</div>
        <div class="stat-value" style="color: var(--warning);">{{ battery.capacityDecayRate || '--' }}%</div>
        <div class="stat-label" style="margin-top: 8px;">评估温度: {{ battery.assessTemperature || '--' }}°C</div>
      </div>
    </div>

    <!-- 电池参数详情 + 衰减曲线 -->
    <div class="charts-row" style="margin-top: 20px;">
      <el-card>
        <h3 class="chart-title">电池参数</h3>
        <el-descriptions :column="2" border style="margin-top: 12px;">
          <el-descriptions-item label="电池编号">{{ battery.batteryCode || 'BAT-001' }}</el-descriptions-item>
          <el-descriptions-item label="电压(V)">{{ battery.currentVoltage || 22.8 }}</el-descriptions-item>
          <el-descriptions-item label="内阻(mΩ)">{{ battery.internalResistance || 45 }}</el-descriptions-item>
          <el-descriptions-item label="温度(°C)">{{ battery.temperature || -18 }}</el-descriptions-item>
          <el-descriptions-item label="循环次数">{{ battery.cycleCount || 128 }}</el-descriptions-item>
          <el-descriptions-item label="标称容量(mAh)">{{ battery.nominalCapacity || 5000 }}</el-descriptions-item>
          <el-descriptions-item label="可用容量(mAh)">{{ battery.availableCapacity || 2800 }}</el-descriptions-item>
        </el-descriptions>
        <el-button type="primary" style="margin-top: 16px; width: 100%;" @click="triggerAiPredict">
          <el-icon><Cpu /></el-icon> 调用AI动力衰减预测
        </el-button>
      </el-card>
      <div class="chart-container">
        <h3 class="chart-title">健康评分历史趋势</h3>
        <v-chart :option="historyChartOption" autoresize style="height: 300px;" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { Cpu } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

use([CanvasRenderer, LineChart, TitleComponent, TooltipComponent, GridComponent])

const selectedDrone = ref('1')
const battery = ref({
  healthScore: 78, currentLevel: 72.5, predictedRange: 5.8, predictedFlightTime: 18.5,
  capacityDecayRate: 44, assessTemperature: -22, batteryCode: 'BAT-001',
  currentVoltage: 22.8, internalResistance: 45, temperature: -18,
  cycleCount: 128, nominalCapacity: 5000, availableCapacity: 2800
})

const historyChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', boundaryGap: false,
    data: ['12:00', '12:10', '12:20', '12:30', '12:40', '12:50', '13:00'],
    axisLabel: { color: '#c0c4cc' }, axisLine: { lineStyle: { color: '#2a3555' } } },
  yAxis: { type: 'value', min: 50, max: 100,
    axisLabel: { color: '#c0c4cc' }, splitLine: { lineStyle: { color: '#2a3555' } } },
  series: [{
    name: '健康评分', type: 'line', smooth: true,
    lineStyle: { color: '#409eff', width: 2 },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: 'rgba(64,158,255,0.3)' }, { offset: 1, color: 'rgba(64,158,255,0.02)' }] } },
    data: [85, 83, 82, 80, 79, 78, 78]
  }]
}))

const getScoreColor = (score) => score > 80 ? '#67c23a' : score > 60 ? '#e6a23c' : '#f56c6c'
const getBatteryColor = (level) => level > 60 ? '#67c23a' : level > 30 ? '#e6a23c' : '#f56c6c'
const triggerAiPredict = () => { ElMessage.info('正在调用AI动力衰减预测...') }
</script>

<style scoped>
.battery-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
</style>
