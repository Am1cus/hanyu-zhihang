<template>
  <div>
    <div class="page-heading">
      <div><div class="eyebrow">Flight observation / 01</div><h1>飞行监测</h1><p>从一段真实输入，看到模型如何给出预测。</p></div>
      <div class="actions">
        <el-button :icon="FolderOpened" @click="showArchive = true">历史实验</el-button>
        <el-button :icon="VideoPlay" @click="showGuide = true">回放说明</el-button>
        <el-button :icon="Download" :disabled="!rows.length" :loading="exporting" @click="exportReplay">导出完整档案</el-button>
      </div>
    </div>

    <div v-if="!system.backendOnline" class="notice error status-notice">后台暂未连接。请启动演示服务；下方如有曲线，仅为最近收到的历史记录。</div>
    <div class="source-bar">
      <div class="source-id"><span class="source-icon"><Position /></span><div><strong>{{ latest?.droneCode || '等待数据源' }}</strong><span>AirSim 仿真遥测 · 非真机实飞</span></div></div>
      <div class="source-meta">
        <span v-if="rows.length" class="mono sample-count">{{ rows.length }} 条 · {{ format(duration, 0) }} s</span>
        <span class="pill" :class="{ idle: !streaming }"><i class="dot" />{{ streaming ? '正在接收' : rows.length ? '暂无新数据 · 显示历史' : '等待回放' }}</span>
      </div>
    </div>

    <div v-if="store.archiveError" class="notice error status-notice">{{ store.archiveError }}</div>
    <div v-if="isV3" class="notice status-notice"><strong>V3 候选研究模式</strong> · {{ evaluationLabel(prediction?.evaluation_role || store.runDetail?.configuration?.evaluation_role) }}。只记录和展示耗电预测，不控制飞行；尚未通过新数据独立确认及真机验证。</div>
    <div v-if="prediction?.outside_training_range_features?.length" class="notice status-notice">当前输入超出训练范围：{{ prediction.outside_training_range_features.join('、') }}。候选输出仅供研究，不代表已验证的可靠预测。</div>
    <section v-if="store.selectedRunId" class="run-context" v-loading="store.loadingArchive">
      <div class="run-context-main">
        <span><strong>{{ store.runDetail?.flightId || latest?.flightId || '正在读取架次' }}</strong><span class="mono run-id">运行 {{ store.selectedRunId }}</span></span>
        <div class="actions">
          <span class="pill idle">{{ store.followLive ? '跟随最新回放' : '历史记录视图' }}</span>
          <el-button v-if="!store.followLive" size="small" @click="resumeLive">返回最新回放</el-button>
          <el-button size="small" :disabled="!validWindows.length" @click="openRecheck">复算已存窗口</el-button>
        </div>
      </div>
      <details v-if="store.runDetail" class="provenance"><summary>查看数据与模型指纹</summary>
        <p>预处理版本：{{ store.runDetail.preprocessingVersion }} · 不插补缺失秒</p>
        <p>数据 SHA-256：<code>{{ store.runDetail.sourceSha256 }}</code></p>
        <p>配置 SHA-256：<code>{{ store.runDetail.configSha256 }}</code></p>
        <p>当前窗口模型：<code>{{ prediction?.model_sha256 || '本窗口尚未产生有效推理' }}</code></p>
        <p>标准化器：<code>{{ prediction?.scaler_sha256 || '—' }}</code></p>
        <p>全架次已保存 {{ store.runDetail.sampleCount }} 条 · 已验证 {{ store.runDetail.metrics?.verified_count || 0 }} 个 · MAPE {{ format(store.runDetail.metrics?.mape_pct, 3) }}%</p>
      </details>
    </section>

    <section class="metrics-grid" aria-label="当前遥测和预测摘要">
      <div class="metric"><span>当前剩余电荷量</span><div class="value">{{ format(latest?.remainingCapacityAh, 4) }}<small>Ah</small></div><p>{{ isV3 ? 'AirSim配套公式电池 · 非真机测量' : '来自 AirSim 电池遥测' }}</p></div>
      <div class="metric"><span>预测未来10秒耗电</span><div class="value prediction-value">{{ format(consumptionMah, 3) }}<small>mAh</small></div><p>{{ prediction?.valid ? 'LSTM 原始输出 · 未平滑' : modelState }}</p></div>
      <div class="metric"><span>10秒后剩余容量</span><div class="value">{{ format(prediction?.valid ? prediction.predicted_capacity_Ah : null, 4) }}<small>Ah</small></div><p>当前容量 − 预测耗电量</p></div>
      <div class="metric"><span>当前视图已验证误差</span><div class="value">{{ format(metrics.mape, 2) }}<small>% MAPE</small></div><p>{{ metrics.count ? metrics.count + ' 个到期预测 · MAE ' + format(metrics.mae, 3) + ' mAh' : '等待预测10秒后的真实值' }}</p></div>
    </section>

    <div class="monitor-grid">
      <section class="panel prediction-panel">
        <div class="panel-head"><div><h2>预测与真实值</h2><p>{{ chartMode === 'consumption' ? '评价模型先看耗电量，而不是被当前容量锚定的总量。' : '预测按目标时刻向后平移10秒，与同一时刻的真实值对照。' }}</p></div>
          <div class="segmented" aria-label="图表指标"><button :class="{ active: chartMode === 'consumption' }" @click="chartMode = 'consumption'">10秒耗电</button><button :class="{ active: chartMode === 'capacity' }" @click="chartMode = 'capacity'">剩余容量</button></div>
        </div>
        <ForecastChart v-if="rows.length" :rows="rows" :mode="chartMode" :zero="zeroAxis" :baselines="isV3" />
        <div v-else class="empty chart-empty"><div class="empty-lines"><span /><span /><span /></div><h3>等待第一段遥测</h3><p>启动 AirSim 架次回放后，曲线会自动出现。<br>累计30条连续输入后，开始执行 LSTM 推理。</p><el-button @click="showGuide = true">查看回放命令</el-button></div>
        <div class="chart-footer"><span>按采集时间对齐 · 无平滑或线性校正</span><label><input v-model="zeroAxis" type="checkbox"> 纵轴从零开始</label></div>
        <div class="chart-note">{{ zeroAxis ? '当前为零基准视图。' : '当前为局部纵轴，适合查看细微偏差；并非从零开始。' }} 耗电真实值须等待后续10秒数据，末尾预测可能尚未验证。</div>
      </section>

      <section class="panel telemetry-panel">
        <div class="panel-head"><h2>输入遥测</h2><span class="muted mono" style="font-size:11px">1 Hz</span></div>
        <div class="panel-body">
          <div class="soc-line"><span>电量 SOC</span><strong>{{ format(latest?.batteryLevel, 1) }}<small>%</small></strong></div>
          <div class="soc-track"><div :style="{ width: Math.max(0, Math.min(100, numeric(latest?.batteryLevel) || 0)) + '%' }" /></div>
          <dl class="telemetry-list">
            <div v-for="item in inputFields" :key="item.key"><dt>{{ item.label }}</dt><dd :class="{ caution: (item.key === 'envTemperature' && latest?.envTemperature <= -25) || (item.key === 'windSpeed' && latest?.windSpeed >= 8) }">{{ format(latest?.[item.key], 2) }} <small>{{ item.unit }}</small></dd></div>
          </dl>
          <div class="sample-time"><span>最新采集时间</span><span class="mono">{{ latest?.collectTime?.replace('T', ' ').slice(0, 19) || '—' }}</span></div>
        </div>
      </section>
    </div>

    <section v-if="isV3" class="panel live-baselines">
      <div class="panel-head"><div><h2>本次回放：同窗口方法对照</h2><p>三个方法使用相同的已到期标签；重复回放不增加独立架次数。</p></div></div>
      <el-table :data="comparison" empty-text="等待未来10秒标签">
        <el-table-column prop="name" label="方法" min-width="200" />
        <el-table-column prop="count" label="共同有效窗口" min-width="125" />
        <el-table-column label="耗电 MAPE ↓" min-width="140"><template #default="{ row }">{{ format(row.mape, 3) }} %</template></el-table-column>
        <el-table-column label="MAE ↓" min-width="130"><template #default="{ row }">{{ format(row.mae, 3) }} mAh</template></el-table-column>
      </el-table>
    </section>

    <section class="panel inference-panel">
      <div class="panel-head"><h2>一次推理如何完成</h2><span class="pill" :class="{ idle: !prediction?.valid, warn: !system.aiStatus.online }">{{ modelState }}</span></div>
      <div class="inference-flow">
        <div><span class="step">01 / 输入窗口</span><strong>{{ windowCount }}<small> / 30 条</small></strong><p>{{ isV3 ? '完整秒均值 → 电流、运动与相对风6维特征' : '温度、风速、电压、电流、SOC、速度、高度' }}</p><div class="window-track"><i v-for="n in 30" :key="n" :class="{ filled: n <= windowCount }" /></div></div>
        <div><span class="step">02 / 模型计算</span><strong>LSTM <small>{{ isV3 ? '32 × 1 · 3成员 FP32' : '64 × 2 · INT8' }}</small></strong><p>{{ isV3 ? '历史耗电 × 学习到的修正倍率 → 三成员均值' : '标准化 → 两层时序网络 → 耗电量输出' }}</p><span class="model-version mono">{{ prediction?.model_version || system.aiStatus.airsimCapacityModelVersion }}</span></div>
        <div><span class="step">03 / 等待验证</span><strong>{{ format(prediction?.valid ? prediction.inference_time_ms : null, 2) }}<small> ms / 推理服务内部</small></strong><p>{{ metrics.count }} 个预测已有真实值 · {{ pending }} 个有效预测未形成有效标签</p><router-link to="/experiments">查看模型与实验记录 →</router-link></div>
      </div>
    </section>

    <div class="bottom-grid">
      <section class="panel">
        <div class="panel-head"><div><h2>相对飞行轨迹</h2><p>来自回放位置记录；不是地图定位，也不是路径规划结果。</p></div><span class="muted" style="font-size:11px">{{ trajectory ? '等比例 · 北向上' : '尚无位置' }}</span></div>
        <div v-if="trajectory" class="trajectory-layout">
          <svg class="trajectory" viewBox="0 0 400 150" role="img" aria-label="AirSim相对轨迹，圆点表示最近收到的位置">
            <path d="M30 30H370M30 75H370M30 120H370M80 20V135M160 20V135M240 20V135M320 20V135" stroke="#e7ebe0" fill="none" />
            <polyline :points="trajectory.points" fill="none" stroke="#6a8460" stroke-width="2" />
            <circle :cx="trajectory.first.x" :cy="trajectory.first.y" r="4" fill="#fff" stroke="#6a8460" stroke-width="2" />
            <circle :cx="trajectory.last.x" :cy="trajectory.last.y" r="5" fill="#39634d" stroke="#fff" stroke-width="2" />
            <text x="365" y="20" fill="#737e69" font-size="10">N ↑</text>
          </svg>
          <div class="trajectory-key"><span><i class="dot" /> 最近位置</span><span class="mono">范围 {{ format(trajectory.width, 0) }} × {{ format(trajectory.height, 0) }} m</span></div>
        </div>
        <div v-else class="empty" style="padding:30px">收到有效位置后绘制轨迹，不填充虚拟无人机。</div>
      </section>
      <section class="panel rule-panel">
        <div class="panel-head"><h2>规则预警</h2><router-link to="/warning">查看记录 →</router-link></div>
        <div class="panel-body"><p class="rule-count"><strong>{{ system.unhandledCount }}</strong> 条待处理</p><p class="footnote">当前采用阈值判断，不是 LSTM 异常识别。</p><div class="rule-tags"><span>温度 ≤ −25°C</span><span>SOC ≤ 20%</span><span>风速 ≥ 8 m/s</span></div><p class="footnote">同一实验同类预警有60秒冷却。待处理数为所有历史实验累计。</p></div>
      </section>
    </div>
    <p class="page-footer">实验数据来自 AirSim。当前页面不提供真机调度、剩余航时或电池健康 SOH 结论。实验已持久保存，重启不会清空。图表最多显示1800条，完整数据可导出。</p>

    <el-dialog v-model="showGuide" title="启动与回放" width="min(650px, 92vw)">
      <p class="footnote">在终端执行。第一条保持运行；第二条在新终端执行。每次回放新建独立实验；已有遥测、预测、预警均保留，不改动原始数据。</p>
      <h3 style="margin-top:20px">1. 启动三个服务</h3><pre>{{ startCommand }}</pre>
      <h3>2. 回放 V3 候选架次</h3><pre>{{ replayCommand }}</pre>
      <p class="footnote">F022 为已参与选型分析的探索性测试架次，不是新的盲测。2 为回放倍速。累计30个完整秒均值后推理，再等待10秒标签；末尾缺标签的预测不参与误差统计。旧数据包仍使用原V2。</p>
      <template #footer><el-button @click="copyReplay">复制回放命令</el-button><el-button type="primary" @click="showGuide = false">知道了</el-button></template>
    </el-dialog>

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
import { VideoPlay, Download, Position, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ForecastChart from '@/components/ForecastChart.vue'
import RunArchive from '@/components/RunArchive.vue'
import { useRoute, useRouter } from 'vue-router'
import { exportRun, recheckRun, getRechecks } from '@/api/runs'
import { useTelemetryStore } from '@/stores/telemetry'
import { useSystemStatusStore } from '@/stores/systemStatus'
import { numeric, format, orderedRows, verifiedPairs, pairMetrics, comparisonMetrics, evaluationLabel, downloadJson } from '@/utils/telemetry'
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
const comparison = computed(() => comparisonMetrics(rows.value))
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
const duration = computed(() => rows.value.length ? (rows.value.at(-1).time - rows.value[0].time) / 1000 : 0)
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
const projectDirectory = '/Users/kedong/Documents/大创项目/LSTM'
const startCommand = 'cd "' + projectDirectory + '"\n./demo/start_demo.sh'
const replayCommand = 'cd "' + projectDirectory + '"\n./demo/replay.sh /Users/kedong/Downloads/dataset_v2.zip F022 2'
async function copyReplay() {
  try { await navigator.clipboard.writeText(replayCommand); ElMessage.success('回放命令已复制') }
  catch { ElMessage.warning('浏览器无法复制，请手动选择上方命令') }
}
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
.live-baselines{margin-top:20px;padding-bottom:10px}
.status-notice{margin-bottom:15px}.source-bar{background:#f0f2e9;border:1px solid #dfe5d6;border-radius:8px;padding:17px 20px;display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;gap:14px}.source-id{display:flex;align-items:center;gap:13px}.source-icon{width:35px;height:35px;background:#e2e9db;border-radius:7px;display:grid;place-items:center}.source-icon svg{width:19px;color:#52714c}.source-id strong{font-size:14px;font-weight:600}.source-id div>span{font-size:11px;color:var(--muted);display:block;margin-top:5px}.source-meta{display:flex;gap:18px;align-items:center}.sample-count{color:var(--muted);font-size:11px}.source-picker{font-size:11px}.metrics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:23px;border:1px solid var(--line);border-radius:9px;background:#fff;padding:22px 0}.metric{padding:0 23px;border-right:1px solid var(--line);min-width:0}.metric:last-child{border:0}.metric>span{color:#6c7665;font-size:12px}.metric .value{margin:10px 0 5px}.metric p{font-size:10px;color:#89907f;line-height:1.8}.prediction-value{color:var(--amber)}.monitor-grid{display:grid;grid-template-columns:minmax(0,1fr) 265px;gap:20px}.prediction-panel{min-width:0}.telemetry-panel{min-width:0}.chart-empty{height:345px;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:24px}.chart-empty .el-button{margin-top:18px}.empty-lines{width:90px;margin-bottom:20px;display:grid;gap:6px}.empty-lines span{height:1px;background:#dfe5d7;transform:rotate(-9deg)}.empty-lines span:nth-child(2){background:#acbe9e}.chart-footer{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:0 23px;font-size:10px;color:var(--muted)}.chart-footer label{display:flex;align-items:center;white-space:nowrap}.chart-footer input{accent-color:var(--green)}.chart-note{padding:10px 23px 17px;color:#8a907f;font-size:10px;line-height:1.7}.soc-line{display:flex;justify-content:space-between;align-items:center;font-size:12px}.soc-line strong{font-size:25px;font-weight:500}.soc-line small{font-size:12px;color:var(--muted);margin-left:3px}.soc-track{height:5px;background:#edf0e6;border-radius:4px;margin-top:12px;overflow:hidden}.soc-track div{background:#66815a;height:100%}.telemetry-list{margin:23px 0 15px}.telemetry-list>div{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid #f0f1eb}.telemetry-list dt{color:var(--muted);font-size:12px}.telemetry-list dd{margin:0;font-size:15px;font-variant-numeric:tabular-nums}.telemetry-list dd small{color:var(--muted);font-size:10px}.caution{color:var(--amber)}.sample-time{display:grid;gap:7px;color:#929786;font-size:10px}.inference-panel{margin-top:20px}.inference-flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));padding:0 23px 22px;gap:24px}.inference-flow>div{padding-left:23px;border-left:1px solid var(--line)}.inference-flow>div:first-child{padding:0;border:0}.step{font-size:10px;color:#8a937d;letter-spacing:1px}.inference-flow strong{display:block;font-size:22px;font-weight:500;margin:13px 0 8px}.inference-flow small{font-size:11px;color:var(--muted);font-weight:400}.inference-flow p{font-size:11px;color:var(--muted);line-height:1.7}.window-track{display:flex;gap:3px;margin-top:14px}.window-track i{height:8px;background:#edf0e7;border-radius:1px;flex:1}.window-track i.filled{background:#97ac88}.model-version{display:block;margin-top:14px;font-size:9px;color:#849078;overflow-wrap:anywhere}.inference-flow a{display:inline-block;margin-top:12px;font-size:11px}.bottom-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:20px;margin-top:20px}.trajectory-layout{padding:0 22px 15px}.trajectory{width:100%;height:145px;background:#f8f9f4;border-radius:6px}.trajectory-key{display:flex;justify-content:space-between;gap:8px;font-size:10px;color:var(--muted);margin-top:9px}.trajectory-key .dot{color:var(--green)}.rule-count{font-size:12px;color:var(--muted);margin:0 0 8px}.rule-count strong{font-size:33px;font-weight:500;color:var(--ink);margin-right:6px}.rule-tags{display:flex;gap:6px;flex-wrap:wrap;margin:18px 0 13px}.rule-tags span{font-size:10px;padding:6px 8px;background:#f4f5ee;border-radius:4px;color:#707b62}.rule-panel a{font-size:11px}.page-footer{font-size:10px;color:#929889;line-height:1.8;margin-top:20px}
@media(max-width:1200px){.monitor-grid{grid-template-columns:minmax(0,1fr) 235px;gap:15px}.metric{padding:0 17px}.metric .value{font-size:26px}.prediction-panel .panel-head{align-items:flex-start;flex-direction:column;gap:12px}}
@media(max-width:950px){.metrics-grid{grid-template-columns:repeat(2,1fr);gap:22px 0}.metric:nth-child(2){border:0}.monitor-grid{grid-template-columns:1fr}.telemetry-list{display:grid;grid-template-columns:repeat(3,1fr);gap:0 20px}.telemetry-list>div{gap:12px}.sample-time{display:flex;justify-content:space-between}.inference-flow{gap:16px}.inference-flow>div{padding-left:16px}.source-bar{flex-wrap:wrap}}
@media(max-width:760px){.source-bar{padding:15px}.source-meta{width:100%;justify-content:space-between}.metric{padding:0 16px}.metric .value{font-size:25px}.inference-flow{grid-template-columns:1fr}.inference-flow>div{border:0;border-top:1px solid var(--line);padding:15px 0 0}.bottom-grid{grid-template-columns:1fr}.telemetry-list{grid-template-columns:repeat(2,1fr);gap:0 16px}.chart-footer{padding:0 17px;flex-wrap:wrap}.chart-note{padding:10px 17px 17px}}
</style>

<style scoped>
.run-context{padding:13px 17px;margin:-7px 0 20px;border:1px solid var(--line);border-radius:7px;background:#fafbf6}.run-context-main{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}.run-context-main strong{font-size:12px}.run-id{font-size:10px;color:var(--muted);margin-left:12px}.provenance{font-size:11px;line-height:1.9;color:var(--muted);margin-top:10px}.provenance summary{cursor:pointer;color:var(--green)}.provenance p{margin-top:6px;overflow-wrap:anywhere}.provenance code{font-size:10px}.recheck-controls{display:flex;gap:12px;margin:20px 0}.recheck-controls .el-select{flex:1}.recheck-result{padding:17px;background:#f4f6ee;border-radius:7px}.recheck-result dl{font-size:12px}.recheck-result dl>div{display:flex;justify-content:space-between;line-height:2}.recheck-result dt{color:var(--muted)}.recheck-result code{font-size:10px;overflow-wrap:anywhere}.recheck-history{display:flex;gap:14px;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--line);font-size:11px;color:var(--muted)}
@media(max-width:760px){.run-id{display:block;margin:5px 0 0;font-size:9px;overflow-wrap:anywhere}.recheck-controls{flex-wrap:wrap}.run-context-main{align-items:flex-start}.run-context-main .actions{width:100%;gap:7px}.recheck-history{font-size:10px;gap:7px}}
</style>
