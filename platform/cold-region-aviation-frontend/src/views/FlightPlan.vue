<template>
  <div class="flight-plan fade-in">
    <div class="page-header">
      <h1 class="page-title">航线规划</h1>
      <el-button type="primary" @click="showPlanDialog = true">
        <el-icon><Plus /></el-icon> 新建航线
      </el-button>
    </div>

    <div class="plan-layout">
      <!-- 航线列表 -->
      <el-card class="plan-list">
        <h3 class="chart-title">航线列表</h3>
        <div v-for="plan in planList" :key="plan.id" class="plan-item" :class="{ active: selectedPlan?.id === plan.id }" @click="selectedPlan = plan">
          <div class="plan-item-header">
            <span class="plan-name">{{ plan.planName }}</span>
            <el-tag :type="getPlanStatusType(plan.status)" size="small">{{ getPlanStatusText(plan.status) }}</el-tag>
          </div>
          <div class="plan-item-info">
            <span>无人机: {{ plan.droneCode }}</span>
            <span>距离: {{ plan.estimatedDistance }}km</span>
          </div>
          <div class="plan-item-info">
            <span>算法: {{ plan.algorithmType === 'ASTAR_IMPROVED' ? '改进A*' : '标准A*' }}</span>
            <span>温度: {{ plan.planTemperature }}°C</span>
          </div>
        </div>
      </el-card>

      <!-- 航线详情 -->
      <el-card class="plan-detail">
        <template v-if="selectedPlan">
          <h3 class="chart-title">{{ selectedPlan.planName }}</h3>
          <el-descriptions :column="2" border style="margin-top: 12px;">
            <el-descriptions-item label="无人机">{{ selectedPlan.droneCode }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="getPlanStatusType(selectedPlan.status)" size="small">{{ getPlanStatusText(selectedPlan.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="规划算法">{{ selectedPlan.algorithmType === 'ASTAR_IMPROVED' ? '改进A*（温度-功耗加权）' : '标准A*' }}</el-descriptions-item>
            <el-descriptions-item label="环境温度">{{ selectedPlan.planTemperature }}°C</el-descriptions-item>
            <el-descriptions-item label="飞行高度">{{ selectedPlan.planAltitude }}m</el-descriptions-item>
            <el-descriptions-item label="飞行速度">{{ selectedPlan.planSpeed }}m/s</el-descriptions-item>
            <el-descriptions-item label="预计航程">{{ selectedPlan.estimatedDistance }}km</el-descriptions-item>
            <el-descriptions-item label="预计时间">{{ selectedPlan.estimatedTime }}min</el-descriptions-item>
            <el-descriptions-item label="预计能耗">{{ selectedPlan.estimatedEnergy }}%</el-descriptions-item>
            <el-descriptions-item label="风速">{{ selectedPlan.planWindSpeed }}m/s</el-descriptions-item>
          </el-descriptions>
          <div style="margin-top: 16px; display: flex; gap: 8px;">
            <el-button type="primary" v-if="selectedPlan.status === 0" @click="updateStatus(selectedPlan.id, 1)">确认航线</el-button>
            <el-button type="success" v-if="selectedPlan.status === 1" @click="updateStatus(selectedPlan.id, 2)">开始执行</el-button>
            <el-button type="danger" v-if="selectedPlan.status < 3" @click="updateStatus(selectedPlan.id, 4)">取消</el-button>
          </div>
        </template>
        <el-empty v-else description="请选择一条航线查看详情" />
      </el-card>
    </div>

    <!-- 新建航线弹窗 -->
    <el-dialog v-model="showPlanDialog" title="新建航线" width="600px" destroy-on-close>
      <el-form :model="planForm" label-width="100px">
        <el-form-item label="航线名称" required>
          <el-input v-model="planForm.planName" placeholder="如：哈尔滨巡检航线01" />
        </el-form-item>
        <el-form-item label="无人机">
          <el-select v-model="planForm.droneId" placeholder="选择无人机">
            <el-option
              v-for="drone in drones" :key="drone.id"
              :label="`${drone.droneCode} ${drone.droneName}`" :value="drone.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="规划算法">
          <el-radio-group v-model="planForm.algorithmType">
            <el-radio value="ASTAR">标准 A*</el-radio>
            <el-radio value="ASTAR_IMPROVED">改进 A*（温度-功耗加权）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="飞行高度(m)">
          <el-input-number v-model="planForm.planAltitude" :min="10" :max="500" />
        </el-form-item>
        <el-form-item label="飞行速度(m/s)">
          <el-input-number v-model="planForm.planSpeed" :min="1" :max="25" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="planForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPlanDialog = false">取消</el-button>
        <el-button type="primary" @click="createPlan">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getFlightPlans, createFlightPlan, updateFlightPlanStatus } from '@/api/flightPlan'
import { getDashboardActiveDrones } from '@/api/warning'

const showPlanDialog = ref(false)
const selectedPlan = ref(null)
const planList = ref([])
const drones = ref([])
const planForm = ref({ algorithmType: 'ASTAR_IMPROVED', planAltitude: 120, planSpeed: 15, droneId: null })

onMounted(async () => {
  const dronesResponse = await getDashboardActiveDrones()
  drones.value = dronesResponse.data || []
  await loadPlans()
})

const loadPlans = async () => {
  const response = await getFlightPlans()
  planList.value = response.data || []
  if (selectedPlan.value) selectedPlan.value = planList.value.find(item => item.id === selectedPlan.value.id) || null
}

const createPlan = async () => {
  const drone = drones.value.find(item => item.id === planForm.value.droneId)
  if (!planForm.value.planName || !drone) {
    ElMessage.warning('请填写航线名称并选择无人机')
    return
  }
  await createFlightPlan({ ...planForm.value, droneCode: drone.droneCode })
  showPlanDialog.value = false
  ElMessage.success('航线创建成功')
  await loadPlans()
}
const updateStatus = async (id, status) => {
  await updateFlightPlanStatus(id, status)
  ElMessage.success('状态已更新')
  await loadPlans()
}
const getPlanStatusType = (s) => ({ 0: 'info', 1: 'primary', 2: 'success', 3: '', 4: 'danger' }[s] || 'info')
const getPlanStatusText = (s) => ({ 0: '草稿', 1: '已确认', 2: '执行中', 3: '已完成', 4: '已取消' }[s] || '未知')
</script>

<style scoped>
.plan-layout { display: grid; grid-template-columns: 360px 1fr; gap: 16px; }
.plan-list { max-height: 600px; overflow-y: auto; }
.plan-item { padding: 14px; border: 1px solid var(--border-color); border-radius: var(--radius-sm); margin-top: 10px; cursor: pointer; transition: all 0.2s; }
.plan-item:hover { border-color: var(--primary); background: var(--bg-card-hover); }
.plan-item.active { border-color: var(--primary); background: rgba(64,158,255,0.1); }
.plan-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.plan-name { font-weight: 600; color: var(--text-primary); }
.plan-item-info { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
</style>
