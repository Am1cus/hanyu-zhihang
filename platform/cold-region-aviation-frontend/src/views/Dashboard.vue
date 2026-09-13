<template>
  <div class="dashboard">
    <div class="page-heading">
      <div><h1>预测看板</h1><p>用过去30秒的数据，预测接下来10秒的耗电。</p></div>
      <div class="actions"><el-button @click="showArchive = true">切换记录</el-button><el-button type="primary" @click="showGuide = true">如何开始回放</el-button></div>
    </div>
    <div v-if="!system.backendOnline" class="notice error status-notice" role="status">后台未连接。请按「使用指南」启动服务；已显示的曲线是历史数据。</div>
    <div v-if="store.archiveError" class="notice error status-notice" role="alert">{{ store.archiveError }}</div>
    <div v-if="prediction?.outside_training_range_features?.length" class="notice error status-notice">输入超出训练范围，结果仅供研究：{{ prediction.outside_training_range_features.join('、') }}。</div>
    <section class="run-strip" aria-label="当前回放">
      <div class="run-identity"><strong>{{ store.runDetail?.flightId || latest?.flightId || '尚未选择架次' }}</strong><span class="pill" :class="{idle:!streaming}"><i class="dot" />{{ streamState }}</span></div>
      <div class="run-actions"><span class="sample-count">{{ rows.length }} 条数据</span><el-button v-if="!store.followLive" @click="resumeLive">跟随最新回放</el-button></div>
    </section>
    <p v-if="rows.length || store.runDetail" class="research-caption"><span class="pill idle">{{ isV3 ? 'LSTM V3候选' : 'LSTM V2' }}</span><span>AirSim仿真 · 未经真机验证</span><span v-if="isV3">{{ evaluationLabel(prediction?.evaluation_role || store.runDetail?.configuration?.evaluation_role) }}</span></p>

    <section v-if="rows.length" class="metrics-grid" aria-label="当前预测结果">
      <div class="metric emphasis"><span>预测未来10秒耗电</span><div class="value">{{ format(consumptionMah, 2) }}<small>mAh</small></div><p>{{ prediction?.valid ? '模型提前给出的结果，未作平滑修正' : modelState }}</p></div>
      <div class="metric"><span>平均预测偏差 <small>越小越好</small></span><div class="value">{{ format(metrics.mape, 2) }}<small>%</small></div><p>{{ metrics.count ? metrics.count + ' 个片段已核对 · 相对误差MAPE' : '还需等待预测后10秒的实际数据' }}</p></div>
      <div class="metric"><span>当前电量 <small>SOC</small></span><div class="value">{{ format(latest?.batteryLevel, 1) }}<small>%</small></div><p>剩余电荷 {{ format(latest?.remainingCapacityAh,4) }} Ah</p></div>
    </section>

    <section class="panel prediction-panel">
      <div class="panel-head">
        <div><h2>{{ chartMode === 'consumption' ? '预测得准不准？' : '剩余电荷如何变化？' }}</h2><p>{{ chartMode === 'consumption' ? '绿色是后续实际耗电，橙色是提前预测。看两条线的差距。' : '将预测移到10秒后的目标时刻，与同一时刻实际值比较。' }}</p></div>
        <div class="segmented" aria-label="图表指标"><button :aria-pressed="chartMode === 'consumption'" :class="{active:chartMode === 'consumption'}" @click="chartMode='consumption'">10秒耗电</button><button :aria-pressed="chartMode === 'capacity'" :class="{active:chartMode === 'capacity'}" @click="chartMode='capacity'">剩余电荷</button></div>
      </div>
      <ForecastChart v-if="rows.length" :rows="rows" :mode="chartMode" :zero="zeroAxis" :baselines="isV3 && showBaselines" />
      <div v-else class="empty chart-empty"><h3>先打开一条记录，或开始实时回放</h3><p>已有实验可以直接查看，不必再次运行模型。<br>开始新回放后，30条连续数据会组成第一次推理的输入。</p><div class="actions"><el-button :disabled="!system.backendOnline" @click="showArchive=true">查看已有记录</el-button><el-button type="primary" @click="showGuide=true">查看启动步骤</el-button></div></div>
      <div class="chart-controls"><label v-if="isV3 && chartMode==='consumption'"><input v-model="showBaselines" type="checkbox"> 同时显示简单方法</label><label><input v-model="zeroAxis" type="checkbox"> 纵轴从零开始</label><router-link v-if="store.selectedRunId" :to="{path:'/experiments',query:{runId:store.selectedRunId}}">比较三种方法 →</router-link></div>
      <p class="chart-note">{{ zeroAxis ? '纵轴从零开始。' : '当前纵轴放大了局部差异，不从零开始。' }} 实际耗电需等待后续10秒；末尾 {{ pending }} 个有效预测尚未形成可用标签。</p>
    </section>

    <section class="progress-strip" aria-label="推理过程">
      <div><span>1. 收集输入</span><strong>{{ windowCount }} / 30 条</strong><p>每秒一条，必须连续</p></div>
      <div><span>2. LSTM预测</span><strong>{{ modelState }}</strong><p>{{ prediction?.valid ? format(prediction.inference_time_ms,2)+' ms · 服务内部耗时' : '输入可用后自动计算' }}</p></div>
      <div><span>3. 等实际值核对</span><strong>{{ metrics.count }} 个片段已核对</strong><p>平均差值 {{ format(metrics.mae,2) }} mAh</p></div>
    </section>

    <details class="disclosure telemetry-detail">
      <summary>查看本次输入数据与相对轨迹</summary>
      <dl class="telemetry-list"><div v-for="item in inputFields" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ format(latest?.[item.key],2) }} {{ item.unit }}</dd></div><div><dt>预测10秒后剩余电荷</dt><dd>{{ format(prediction?.valid ? prediction.predicted_capacity_Ah : null,4) }} Ah</dd></div><div><dt>最新源数据时间</dt><dd>{{ latest?.collectTime?.replace('T',' ').slice(0,19) || '—' }}</dd></div></dl>
      <div v-if="trajectory" class="trajectory-layout"><svg class="trajectory" viewBox="0 0 400 150" role="img" aria-label="AirSim相对轨迹，实心圆为最后位置"><path d="M30 30H370M30 75H370M30 120H370M80 20V135M160 20V135M240 20V135M320 20V135" stroke="#dce3e0" fill="none"/><polyline :points="trajectory.points" fill="none" stroke="#235e49" stroke-width="2"/><circle :cx="trajectory.first.x" :cy="trajectory.first.y" r="4" fill="#fff" stroke="#235e49" stroke-width="2"/><circle :cx="trajectory.last.x" :cy="trajectory.last.y" r="5" fill="#235e49" stroke="#fff" stroke-width="2"/><text x="355" y="20" fill="#56645f" font-size="13">N ↑</text></svg><p class="footnote">相对轨迹约 {{ format(trajectory.width,0) }} × {{ format(trajectory.height,0) }} m；不是地图定位或规划结果。</p></div>
      <p class="footnote">仿真电池由公式生成，不是真实电池测量。V3使用电流、运动与相对风特征，未直接输入温度。</p>
    </details>

    <details v-if="store.selectedRunId" class="disclosure provenance">
      <summary>实验档案：导出、复算与版本信息</summary>
      <div class="actions"><el-button :loading="exporting" :disabled="!rows.length" @click="exportReplay">导出完整档案</el-button><el-button :disabled="!validWindows.length" @click="openRecheck">复算已存窗口</el-button></div>
      <p class="run-id">运行编号 <code>{{ store.selectedRunId }}</code></p>
      <template v-if="store.runDetail"><p>预处理：<code>{{ store.runDetail.preprocessingVersion }}</code> · 不插补缺失秒</p><p>数据SHA-256：<code>{{ store.runDetail.sourceSha256 }}</code></p><p>配置SHA-256：<code>{{ store.runDetail.configSha256 }}</code></p></template>
      <p>模型版本：<code>{{ prediction?.model_version || '本窗口暂无结果' }}</code></p><p>模型SHA-256：<code>{{ prediction?.model_sha256 || '—' }}</code></p><p>标准化器SHA-256：<code>{{ prediction?.scaler_sha256 || '—' }}</code></p>
      <p class="footnote">V3是32单元单层LSTM的三个FP32成员集成。原预测不会被复算覆盖；复算一致只证明可复现，不代表预测准确。</p>
    </details>
    <div class="warning-link"><p>所有实验累计 <strong>{{ system.unhandledCount }}</strong> 条预警待处理，来自温度、电量或风速阈值。</p><router-link to="/warning">查看预警记录 →</router-link></div>
    <p class="footnote page-footer">当前不提供剩余航时、SOH或自动返航结论。网页显示最近1800条；完整记录可在实验档案中导出。</p>
    <QuickStartDialog v-model="showGuide" />
    <RunArchive v-model="showArchive" @open-run="openArchiveRun" />
    <el-dialog v-model="showRecheck" title="复算已存窗口" width="min(690px, 94vw)">
      <p class="footnote">后台读取原始存档输入，重新调用当前模型。先核对模型与标准化器指纹，再比较输出；原预测不会被覆盖。一致性不是预测准确率。</p>
      <p class="footnote">已锁定本次复算所属实验：<code>{{ recheckRunId }}</code>。新回放不会改变这个选择。</p>
      <div class="recheck-controls"><el-select v-model="recheckSeq" aria-label="待复算窗口">
        <el-option v-for="row in recheckWindows" :key="row.sampleSeq" :value="row.sampleSeq" :label="'源时间 ' + row.sourceTimeS + 's · 样本 ' + row.sampleSeq" />
      </el-select><el-button type="primary" :loading="rechecking" :disabled="recheckSeq === null" @click="runRecheck">运行一次复算</el-button></div>
      <el-alert v-if="recheckError" :title="recheckError" type="error" :closable="false" />
      <div v-if="recheckResult" class="recheck-result">
        <span class="pill" :class="{ warn: !recheckResult.consistent }">{{ recheckResult.consistent ? '复算一致 · 原记录未改动' : '未通过一致性核对' }}</span>
        <p v-if="!recheckResult.consistent" class="footnote">{{ recheckReasons[recheckResult.reason] || recheckResult.reason }}</p>
        <dl><div><dt>存档耗电预测</dt><dd>{{ format(recheckResult.original?.predicted_consumption_Ah, 6) }} Ah</dd></div><div><dt>本次重新计算</dt><dd>{{ format(recheckResult.recomputed?.predicted_consumption_Ah, 6) }} Ah</dd></div><div><dt>允许数值差</dt><dd>{{ recheckResult.toleranceAh }} Ah</dd></div></dl>
        <p class="footnote">输入指纹 <code>{{ recheckResult.inputSha256 }}</code></p>
      </div>
      <h3 style="margin:22px 0 10px">最近复算记录</h3>
      <p v-if="!recheckHistory.length" class="footnote">尚无复算记录。执行后会持久保存。</p>
      <div v-for="item in recheckHistory.slice(0,5)" :key="item.recheckId" class="recheck-history"><span>{{ item.checkedAt?.replace('T',' ').slice(0,19) }}</span><span>样本 {{ item.sampleSeq }}</span><span>{{ item.consistent ? '一致' : '不一致 / 不可用' }}</span></div>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import ForecastChart from '@/components/ForecastChart.vue'
import RunArchive from '@/components/RunArchive.vue'
import QuickStartDialog from '@/components/QuickStartDialog.vue'
import { streamLabel } from '@/utils/presentation'
import { useRoute, useRouter } from 'vue-router'
import { exportRun, recheckRun, getRechecks } from '@/api/runs'
import { useTelemetryStore } from '@/stores/telemetry'
import { useSystemStatusStore } from '@/stores/systemStatus'
import { numeric, format, verifiedPairs, pairMetrics, evaluationLabel, downloadJson } from '@/utils/telemetry'
const store = useTelemetryStore()
const system = useSystemStatusStore()
const route = useRoute(), router = useRouter()
const rows = computed(() => store.rows)
const showArchive = ref(false), exporting = ref(false)
const showRecheck = ref(false), rechecking = ref(false), recheckSeq = ref(null)
const recheckRunId = ref(null), recheckWindows = ref([])
const recheckResult = ref(null), recheckError = ref(''), recheckHistory = ref([])
const validWindows = computed(() => rows.value.filter(row => row.prediction?.valid))
const recheckReasons = { artifact_mismatch: '当前模型或标准化器与存档版本不同，不能认定为同版本复算。', output_mismatch: '相同版本的输出差异超出允许范围，请检查运行环境。', ai_unavailable: 'AI服务不可用，原预测仍保留。' }
watch(() => route.query.runId, id => {
  if (typeof id === 'string') store.openRun(id)
  else store.resumeLive()
}, { immediate: true })
watch(() => store.selectedRunId, () => store.refreshDetail())
function openArchiveRun(id) { router.replace({ path: '/dashboard', query: { runId: id } }) }
function resumeLive() { router.replace({ path: '/dashboard' }); store.resumeLive() }
async function openRecheck() {
  recheckRunId.value = store.selectedRunId
  recheckWindows.value = validWindows.value.map(row => ({ sampleSeq: row.sampleSeq, sourceTimeS: row.sourceTimeS }))
  recheckSeq.value = recheckWindows.value[0]?.sampleSeq ?? null
  recheckResult.value = null; recheckError.value = ''; showRecheck.value = true
  try { recheckHistory.value = (await getRechecks(recheckRunId.value)).data || [] }
  catch { recheckHistory.value = []; recheckError.value = '无法读取复算历史。' }
}
async function runRecheck() {
  const id = recheckRunId.value
  if (!id || recheckSeq.value === null) return
  rechecking.value = true; recheckError.value = ''
  try {
    recheckResult.value = (await recheckRun(id, recheckSeq.value)).data
    recheckHistory.value = (await getRechecks(id)).data || []
  } catch { recheckError.value = '复算请求未完成，请确认后台和AI服务在线。' }
  finally { rechecking.value = false }
}
const latest = computed(() => rows.value.at(-1))
const prediction = computed(() => latest.value?.prediction)
const isV3 = computed(() => prediction.value?.execution_mode === 'research_shadow' || store.runDetail?.configuration?.execution_mode === 'research_shadow')
const showBaselines = ref(false)
const streamState = computed(() => streamLabel({followLive:store.followLive, streaming:streaming.value, count:rows.value.length, status:store.runDetail?.status, connected:store.connected}))
const consumptionMah = computed(() => {
  const value = numeric(prediction.value?.predicted_consumption_Ah)
  return prediction.value?.valid && value !== null ? value * 1000 : null
})
const now = ref(Date.now())
let timer, detailTimer
onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 1000)
  detailTimer = setInterval(() => { if (store.followLive) store.refreshDetail() }, 5000)
})
onUnmounted(() => { clearInterval(timer); clearInterval(detailTimer) })
const streaming = computed(() => store.followLive && store.connected && latest.value?.receivedAt && now.value - latest.value.receivedAt < 3500)
const metrics = computed(() => pairMetrics(verifiedPairs(rows.value)))
const pending = computed(() => rows.value.filter(row => row.prediction?.valid).length - metrics.value.count)
const windowCount = computed(() => {
  if (numeric(prediction.value?.window_samples) !== null) return prediction.value.window_samples
  const match = prediction.value?.reason?.match(/collecting_window: (\d+)/)
  return match ? Number(match[1]) : Math.min(rows.value.length, 30)
})
const modelState = computed(() => {
  if (prediction.value?.valid) return streaming.value ? '已输出有效预测' : '存档有效预测'
  if (!rows.value.length) return '等待输入'
  const reason = prediction.value?.reason || ''
  if (reason.includes('ai_service_unavailable')) return '该窗口AI服务不可用'
  if (reason.includes('missing_field') || reason.includes('out_of_range')) return '输入缺失或越界 · 不推理'
  if (reason.includes('gap')) return '时间或序号断点 · 重新收集窗口'
  return windowCount.value < 30 ? '正在收集连续输入窗口' : '预测不可用'
})
const inputFields = [
  { key: 'envTemperature', label: '环境温度', unit: '°C' }, { key: 'windSpeed', label: '风速', unit: 'm/s' },
  { key: 'voltage', label: '电压', unit: 'V' }, { key: 'current', label: '电流', unit: 'A' },
  { key: 'speed', label: '飞行速度', unit: 'm/s' }, { key: 'altitude', label: '高度', unit: 'm' }
]
const chartMode = ref('consumption')
const zeroAxis = ref(false)
const showGuide = ref(false)
async function exportReplay() {
  if (!store.selectedRunId) return
  exporting.value = true
  try {
    const archive = await exportRun(store.selectedRunId)
    downloadJson(archive, archive.run.flightId + '-' + archive.run.runId.slice(0,8) + '.json')
  } catch { ElMessage.error('完整档案导出失败，请检查后台连接') }
  finally { exporting.value = false }
}
const trajectory = computed(() => {
  const positions = rows.value.filter(row => numeric(row.latitude) !== null && numeric(row.longitude) !== null)
  if (!positions.length) return null
  const first = positions[0]
  const points = positions.map(row => ({ x: (row.longitude - first.longitude) * 111320 * Math.cos(first.latitude * Math.PI / 180), y: (row.latitude - first.latitude) * 111320 }))
  const minX = Math.min(...points.map(p => p.x)), maxX = Math.max(...points.map(p => p.x))
  const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y))
  const scale = Math.min(330 / Math.max(1, maxX - minX), 105 / Math.max(1, maxY - minY))
  const mapped = points.map(p => ({ x: 200 + (p.x - (minX + maxX) / 2) * scale, y: 77 - (p.y - (minY + maxY) / 2) * scale }))
  return { points: mapped.map(p => p.x + ',' + p.y).join(' '), first: mapped[0], last: mapped.at(-1), width: maxX - minX, height: maxY - minY }
})
</script>
<style scoped>
.status-notice{margin-bottom:14px}.run-strip{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 18px;border:1px solid var(--line);background:#fff;border-radius:10px}.run-identity,.run-actions{display:flex;align-items:center;gap:14px;flex-wrap:wrap}.run-identity strong{font-size:1.125rem}.sample-count{font-size:.875rem;color:var(--muted)}.research-caption{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0 18px;color:var(--muted);font-size:.8125rem;line-height:1.6}
.metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:18px}.metric{padding:18px 20px;border:1px solid var(--line);border-radius:10px;background:#fff}.metric.emphasis{border-color:#c7d8ce;background:#f6faf7;border-top:3px solid var(--green);padding-top:16px}.metric>span{font-size:.875rem;color:var(--muted)}.metric small{font-size:.8125rem;font-weight:400;margin-left:5px}.metric .value{margin:8px 0 5px}.metric p{font-size:.8125rem;color:var(--muted);line-height:1.6}.metric.emphasis .value{color:var(--green)}
.prediction-panel .panel-head{align-items:flex-start}.chart-controls{display:flex;gap:20px;align-items:center;flex-wrap:wrap;padding:8px 24px 0;font-size:.875rem;color:var(--muted)}.chart-controls label{display:flex;align-items:center;gap:7px;min-height:36px;cursor:pointer}.chart-controls input{width:17px;height:17px;accent-color:var(--green)}.chart-controls a{margin-left:auto}.chart-note{padding:6px 24px 18px;color:var(--muted);font-size:.8125rem;line-height:1.7}.chart-empty{min-height:300px;display:flex;flex-direction:column;justify-content:center}
.progress-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;padding:24px 0}.progress-strip>div{border-left:3px solid #cadbd1;padding-left:16px}.progress-strip span,.progress-strip p{display:block;font-size:.875rem;color:var(--muted);line-height:1.7}.progress-strip strong{display:block;font-size:1rem;margin:5px 0}.disclosure{margin-bottom:14px}.telemetry-list{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;margin:20px 0}.telemetry-list dt{font-size:.875rem;color:var(--muted);margin-bottom:8px}.telemetry-list dd{margin:0;font-size:1rem;overflow-wrap:anywhere}.trajectory-layout{max-width:600px;margin:20px 0}.trajectory{height:180px;width:100%;background:#f3f6f4;border-radius:8px}.provenance p{margin-top:12px;line-height:1.8;font-size:.875rem;overflow-wrap:anywhere}.warning-link{display:flex;justify-content:space-between;gap:16px;align-items:center;margin:20px 0;font-size:.875rem;color:var(--muted);line-height:1.7}.page-footer{font-size:.8125rem}
.recheck-controls{display:flex;gap:12px;margin:20px 0}.recheck-controls .el-select{flex:1}.recheck-result{padding:17px;background:var(--soft);border-radius:8px}.recheck-result dl{font-size:.875rem}.recheck-result dl>div{display:flex;justify-content:space-between;gap:12px;line-height:2}.recheck-result dt{color:var(--muted)}.recheck-history{display:flex;gap:14px;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line);font-size:.8125rem;color:var(--muted)}
@media(max-width:1100px){.metric{padding:16px}.metric .value{font-size:1.75rem}.telemetry-list{grid-template-columns:repeat(2,minmax(0,1fr))}.prediction-panel .panel-head{flex-wrap:wrap}}
@media(max-width:760px){.run-strip{flex-wrap:wrap;padding:14px}.research-caption{gap:8px}.research-caption>span:last-child{flex-basis:100%}.metrics-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.metric.emphasis{grid-column:1/-1}.metric .value{font-size:1.625rem}.metric p{font-size:.8125rem}.chart-controls{padding:8px 16px 0;gap:10px}.chart-controls a{margin-left:0;flex-basis:100%}.chart-note{padding:8px 16px 18px}.progress-strip{grid-template-columns:1fr;gap:16px}.progress-strip>div{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px}.progress-strip p{grid-column:1/-1}.progress-strip strong{margin:0}.warning-link,.recheck-controls,.recheck-history{flex-wrap:wrap}.provenance .actions{align-items:stretch}}
</style>
