<template>
  <div>
    <div class="page-heading">
      <div><h1>预警记录</h1><p>查看为什么触发预警，再记录你的处理结果。</p></div>
      <div class="actions"><el-button :icon="Refresh" :loading="loading" @click="fetchWarnings(true)">刷新记录</el-button><el-button :icon="Download" :disabled="!warningList.length" @click="downloadJson(warningList, 'warning-page-' + page.current + '.json')">导出当前页</el-button></div>
    </div>
    <div class="warning-summary"><div><strong>{{ system.unhandledCount }}</strong><span>条待处理</span></div><p>温度 ≤ −25°C · 电量 ≤ 20% · 风速 ≥ 8 m/s<br><span>这是阈值预警，不是AI异常识别；同一实验同类预警冷却60秒。</span></p><el-button @click="showPending">只看待处理</el-button></div>
    <div v-if="error" class="notice error" style="margin-bottom:16px">{{ error }} 已显示的记录可能不是最新状态。</div>
    <section class="panel">
      <form class="filter-bar" @submit.prevent="search">
        <label>类型<select v-model="filters.warningType"><option value="">全部类型</option><option value="TEMPERATURE">低温</option><option value="BATTERY">电量</option><option value="WIND">风速</option></select></label>
        <label>级别<select v-model="filters.warningLevel"><option value="">全部级别</option><option value="1">注意</option><option value="2">警告</option><option value="3">危险</option><option value="4">紧急</option></select></label>
        <label>状态<select v-model="filters.handleStatus"><option value="">全部状态</option><option value="0">待处理</option><option value="1">已处理</option><option value="2">已忽略</option></select></label>
        <el-button type="primary" native-type="submit">查询</el-button><el-button @click="resetFilters">重置筛选</el-button>
        <span class="auto-refresh">每3秒更新</span>
      </form>
      <div class="table-wrap">
        <el-table :data="warningList" v-loading="loading" row-key="id" empty-text="当前筛选下没有预警记录">
          <el-table-column type="expand"><template #default="{ row }"><div class="warning-detail"><p>{{ row.message }}</p><p>触发值：温度 {{ format(row.triggerTemperature, 2) }} °C / SOC {{ format(row.triggerBatteryLevel, 2) }} % / 风速 {{ format(row.triggerWindSpeed, 2) }} m/s</p><p>处理说明：{{ row.handleResult || '尚未记录' }}</p><p>处理时间：{{ dateTime(row.handleTime) }}</p><router-link v-if="row.runId" :to="{path:'/dashboard',query:{runId:row.runId}}">查看关联实验 →</router-link></div></template></el-table-column>
          <el-table-column label="记录时间" width="165"><template #default="{ row }"><span class="time-cell">{{ dateTime(row.warningTime) }}</span></template></el-table-column>
          <el-table-column prop="droneCode" label="数据源" min-width="110" />
          <el-table-column label="类型" width="75"><template #default="{ row }">{{ typeText(row.warningType) }}</template></el-table-column>
          <el-table-column prop="title" label="触发事件" min-width="215" />
          <el-table-column label="级别" width="75"><template #default="{ row }"><span class="pill" :class="row.warningLevel >= 3 ? 'critical' : 'warn'">{{ levelText(row.warningLevel) }}</span></template></el-table-column>
          <el-table-column label="状态" width="90"><template #default="{ row }"><span :class="row.handleStatus === 0 ? 'pending-status' : 'muted'">{{ statusText(row.handleStatus) }}</span></template></el-table-column>
          <el-table-column label="操作" width="125" fixed="right"><template #default="{ row }"><el-button v-if="row.handleStatus === 0" size="small" link type="primary" @click="openHandle(row)">记录处理结果</el-button><span v-else class="muted" style="font-size:0.875rem">展开查看说明</span></template></el-table-column>
        </el-table>
      </div>
      <div class="warning-cards" v-loading="loading">
        <p v-if="!warningList.length" class="empty">当前筛选下没有预警记录。</p>
        <article v-for="row in warningList" :key="row.id" class="warning-card">
          <div class="warning-card-head"><span class="pill" :class="row.warningLevel >= 3 ? 'critical' : 'warn'">{{ levelText(row.warningLevel) }} · {{ typeText(row.warningType) }}</span><span>{{ statusText(row.handleStatus) }}</span></div>
          <h3>{{ row.title }}</h3><p>{{ row.droneCode }} · {{ dateTime(row.warningTime) }}</p>
          <details><summary>触发原因与处理记录</summary><p>{{ row.message }}</p><p>温度 {{ format(row.triggerTemperature,2) }}°C · 电量 {{ format(row.triggerBatteryLevel,1) }}% · 风速 {{ format(row.triggerWindSpeed,2) }}m/s</p><p>处理说明：{{ row.handleResult || '尚未记录' }}</p><router-link v-if="row.runId" :to="{path:'/dashboard',query:{runId:row.runId}}">查看关联实验 →</router-link></details>
          <el-button v-if="row.handleStatus===0" plain type="primary" @click="openHandle(row)">记录处理结果</el-button>
        </article>
      </div>
      <div class="pagination-bar"><span>展开每条记录可查看触发值与处理说明</span><el-pagination v-model:current-page="page.current" :page-size="page.size" :total="page.total" layout="total, prev, pager, next" @current-change="fetchWarnings(true)" /></div>
    </section>
    <p class="footnote" style="margin-top:16px">预警已持久保存，回放或重启不会删除。待处理数为所有实验累计；展开记录可查看所属架次。</p>
    <el-dialog v-model="dialogVisible" title="记录处理结果" width="min(540px, 92vw)">
      <p class="dialog-event">{{ selected?.droneCode }} · {{ selected?.title }}</p>
      <el-form label-position="top">
        <el-form-item label="处理方式"><el-radio-group v-model="resolution.status"><el-radio :value="1">标记为已处理</el-radio><el-radio :value="2">忽略并说明原因</el-radio></el-radio-group></el-form-item>
        <el-form-item label="处理说明（必填）"><el-input v-model="resolution.note" type="textarea" :rows="4" maxlength="300" show-word-limit placeholder="说明观察到的情况和已采取的措施。此操作只记录结果，不会向无人机发送指令。" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!resolution.note.trim()" @click="saveResolution">保存处理结果</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Refresh, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getWarningList, handleWarning } from '@/api/warning'
import { useSystemStatusStore } from '@/stores/systemStatus'
import { format, downloadJson } from '@/utils/telemetry'
const system = useSystemStatusStore()
const warningList = ref([]), loading = ref(false), error = ref('')
const filters = ref({ warningType: '', warningLevel: '', handleStatus: '' })
const appliedFilters = ref({})
const page = ref({ current: 1, size: 10, total: 0 })
const dialogVisible = ref(false), selected = ref(null), saving = ref(false)
const resolution = ref({ status: 1, note: '' })
let timer, requestId = 0
async function fetchWarnings(showLoading = false) {
  const thisRequest = ++requestId
  if (showLoading) loading.value = true
  try {
    const response = await getWarningList({ pageNum: page.value.current, pageSize: page.value.size, ...appliedFilters.value }, { silent: true })
    if (thisRequest !== requestId) return
    warningList.value = response.data?.records || []
    page.value.total = Number(response.data?.total || 0)
    error.value = ''
  } catch {
    if (thisRequest === requestId) error.value = '预警记录读取失败，请检查后台连接后刷新。'
  } finally { if (thisRequest === requestId) loading.value = false }
}
function search() {
  appliedFilters.value = Object.fromEntries(Object.entries(filters.value).filter(([,v]) => v !== ''))
  page.value.current = 1
  fetchWarnings(true)
}
function resetFilters() { filters.value = { warningType: '', warningLevel: '', handleStatus: '' }; search() }
function showPending() { filters.value = { warningType: '', warningLevel: '', handleStatus: '0' }; search() }
function openHandle(row) { selected.value = row; resolution.value = { status: 1, note: '' }; dialogVisible.value = true }
async function saveResolution() {
  if (!resolution.value.note.trim() || saving.value) return
  saving.value = true
  try {
    const response = await handleWarning(selected.value.id, resolution.value.status, resolution.value.note.trim())
    if (response.data !== true) throw new Error('记录未更新')
    dialogVisible.value = false
    ElMessage.success('处理结果已保存')
    await Promise.all([fetchWarnings(true), system.refresh()])
  } catch { ElMessage.error('保存失败，请刷新确认记录是否仍存在') }
  finally { saving.value = false }
}
const typeText = value => ({ TEMPERATURE: '低温', BATTERY: '电量', WIND: '风速', SIGNAL: '信号' }[value] || value)
const levelText = value => ({ 1: '注意', 2: '警告', 3: '危险', 4: '紧急' }[value] || '未知')
const statusText = value => ({ 0: '待处理', 1: '已处理', 2: '已忽略' }[value] || '未知')
const dateTime = value => value ? String(value).replace('T', ' ').slice(0,19) : '—'
onMounted(() => { fetchWarnings(true); timer = setInterval(() => { if (!document.hidden && !loading.value && !saving.value) fetchWarnings() }, 3000) })
onUnmounted(() => { clearInterval(timer); requestId++ })
</script>
<style scoped>
.warning-summary{display:flex;align-items:center;gap:32px;border:1px solid #e4dfcc;background:#f3f0e4;border-radius:9px;padding:24px;margin-bottom:24px}.warning-summary>div{display:flex;align-items:baseline;gap:10px;white-space:nowrap}.warning-summary strong{font-size:2.25rem;font-weight:500;color:#8d744a}.warning-summary span{font-size:0.875rem;color:#8e8975}.warning-summary p{font-size:0.875rem;color:#797662;line-height:2}.warning-summary p span{font-size:0.875rem;color:#9a9686}.warning-summary .el-button{margin-left:auto}.filter-bar{display:flex;align-items:end;gap:12px;flex-wrap:wrap;padding:22px}.filter-bar label{display:grid;gap:8px;font-size:0.875rem;color:var(--muted)}select{height:40px;min-width:115px;padding:0 28px 0 10px;border:1px solid var(--line);border-radius:5px;background:white;color:var(--ink);font-size:0.875rem}.auto-refresh{margin-left:auto;font-size:0.875rem;color:#929987;line-height:32px}.table-wrap{padding:0 22px}.time-cell{font-size:0.875rem;font-variant-numeric:tabular-nums}.pending-status{color:#a16b33;font-size:0.875rem}.critical{color:#a34733;background:#fff0e9}.warning-detail{padding:15px 45px;color:var(--muted);font-size:0.875rem;line-height:2}.pagination-bar{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:22px}.pagination-bar>span{font-size:0.875rem;color:#929987}.dialog-event{font-size:0.875rem;margin-bottom:24px;color:var(--muted)}
@media(max-width:1050px){.warning-summary{gap:20px;flex-wrap:wrap}.warning-summary .el-button{margin-left:0}.pagination-bar{flex-wrap:wrap}}
@media(max-width:760px){.warning-summary{padding:18px}.filter-bar{padding:17px;gap:10px}.filter-bar label{flex:1;min-width:90px}.filter-bar select{width:100%;min-width:90px}.auto-refresh{display:none}.table-wrap{padding:0 10px}.pagination-bar{padding:17px}.warning-detail{padding:10px 25px}}
.warning-cards{display:none}.warning-summary span,.warning-summary p,.warning-summary p span,.pagination-bar>span{color:var(--muted)}.warning-summary{background:#fff7eb;border-color:#e7d9c4}.warning-summary strong{color:#875211}
@media(max-width:760px){.table-wrap{display:none}.warning-cards{display:grid;gap:12px;padding:0 16px}.warning-card{border:1px solid var(--line);border-radius:8px;padding:16px}.warning-card-head{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:.875rem}.warning-card h3{line-height:1.6;margin:12px 0 8px}.warning-card p{font-size:.8125rem;line-height:1.8;color:var(--muted);margin:8px 0;overflow-wrap:anywhere}.warning-card details{font-size:.875rem;margin:14px 0}.warning-card .el-button{width:100%}.pagination-bar{justify-content:center}.pagination-bar>span{display:none}}
</style>
