<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import MissionMap from './components/MissionMap.vue'
import EnergyBudget from './components/EnergyBudget.vue'
import EnergyTrace from './components/EnergyTrace.vue'
import { decisionLabels, reasonText } from './text'

const page = ref('preview')
const catalog = ref(null)
const evaluation = ref(null)
const currentRun = ref(null)
const archiveRun = ref(null)
const history = ref([])
const config = ref({ scenario_id: 'normal-s1', strategy: 'energy', temperature_c: -10, reserve_fraction: 0.2, speedup: 20 })
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const addObstacle = ref(false)
const windX = ref(4)
const windY = ref(0)
const lastUpdate = ref(null)
const pollingError = ref('')
const viewId = ref(null)
let pollTimer = null
let pollInFlight = false
let pollController = null
let disposed = false
let pollVersion = 0

const scenes = computed(() => catalog.value?.scenarios || [])
const selectedScene = computed(() => scenes.value.find((item) => item.id === config.value.scenario_id))
const parameters = computed(() => catalog.value?.parameter_status || {})
const temperatures = computed(() => parameters.value.temperatures_c || [])
const distanceRun = computed(() => evaluation.value?.runs?.find((item) => item.strategy === 'distance'))
const energyRun = computed(() => evaluation.value?.runs?.find((item) => item.strategy === 'energy'))
const selectedEvaluation = computed(() => config.value.strategy === 'energy' ? energyRun.value : distanceRun.value)
const previewBudget = computed(() => evaluation.value?.whole_mission_budget?.[config.value.strategy] || selectedEvaluation.value?.initial_whole_mission_budget || null)
const telemetry = computed(() => currentRun.value?.telemetry?.at(-1))
const running = computed(() => currentRun.value?.runtime_available !== false && currentRun.value?.status === 'RUNNING')
const controllable = computed(() => currentRun.value?.runtime_available !== false && ['RUNNING', 'PAUSED'].includes(currentRun.value?.status))
const oldSession = computed(() => currentRun.value?.runtime_available === false && ['RUNNING', 'PAUSED'].includes(currentRun.value?.status))
const scenarioNames = computed(() => Object.fromEntries(scenes.value.map((item) => [item.id, item.name])))
const pageMeta = {
  preview: { eyebrow: '01 / 出发前', title: '把巡检任务，算清楚。', description: '在同一情景里预演三点巡检与返程，比较距离和能量两种策略。' },
  running: { eyebrow: '02 / 任务中', title: '条件变了，重新判断。', description: '位置由后端仿真推进；风与障碍事件进入真实任务记录。' },
  review: { eyebrow: '03 / 任务后', title: '让每次判断，都能复查。', description: '保留配置、遥测、决策和事件；复演另建记录，原档案持续保留。' },
}
const statusLabels = { RUNNING: '运行中', PAUSED: '已暂停', COMPLETED: '运行已结束', CANCELLED: '已取消', FAILED: '任务失败', UNAVAILABLE: '信息不足' }
const number = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—'
const percent = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : '—'
const runStatus = (value) => statusLabels[value] || value || '等待运行'
const strategyName = (value) => value === 'distance' ? '距离策略' : '能量策略'
const sourceText = computed(() => {
  const source = parameters.value.source
  return typeof source === 'string' ? source : source ? JSON.stringify(source, null, 2) : '后端尚未提供参数来源。'
})

function stopPolling() {
  pollVersion += 1
  clearTimeout(pollTimer)
  pollTimer = null
  pollController?.abort()
}

function schedulePoll(delay = 200) {
  clearTimeout(pollTimer)
  if (!disposed && running.value) pollTimer = setTimeout(poll, delay)
}

async function poll() {
  if (disposed || !running.value || pollInFlight || !currentRun.value?.id) return
  const id = currentRun.value.id
  const version = pollVersion
  pollInFlight = true
  pollController = new AbortController()
  let failed = false
  try {
    const value = await api.run(id, pollController.signal)
    if (!disposed && currentRun.value?.id === id && version === pollVersion) {
      currentRun.value = value
      lastUpdate.value = new Date()
      pollingError.value = ''
    }
  } catch (cause) {
    if (cause.name !== 'AbortError' && !disposed && version === pollVersion) {
      pollingError.value = reasonText(cause.message)
      failed = true
    }
  } finally {
    pollInFlight = false
    pollController = null
    if (!disposed && currentRun.value?.id === id && version === pollVersion && running.value) schedulePoll(failed ? 1000 : 200)
    else if (!disposed && currentRun.value?.id === id && version === pollVersion) loadHistory()
  }
}

watch(() => [currentRun.value?.id, currentRun.value?.status, currentRun.value?.runtime_available], () => {
  if (running.value) schedulePoll()
  else stopPolling()
})
watch(() => [config.value.scenario_id, config.value.temperature_c, config.value.reserve_fraction], () => { evaluation.value = null })
watch(page, (value) => {
  addObstacle.value = false
  if (value === 'review') loadHistory()
})

async function act(action) {
  if (busy.value) return
  busy.value = true
  stopPolling()
  error.value = ''
  notice.value = ''
  try { await action() } catch (cause) { error.value = reasonText(cause.message) }
  finally { busy.value = false; if (running.value) schedulePoll() }
}

async function loadHistory() {
  try {
    const result = await api.runs()
    if (!disposed) history.value = result.runs || []
  } catch (cause) { if (!disposed) error.value = reasonText(cause.message) }
}

async function evaluate() {
  await act(async () => { evaluation.value = await api.evaluate({ ...config.value }) })
}

async function createRun() {
  await act(async () => {
    currentRun.value = await api.createRun({ ...config.value })
    lastUpdate.value = new Date()
    page.value = 'running'
  })
}

async function demo() {
  if (busy.value) return
  config.value = { ...config.value, ...catalog.value?.defaults, speedup: 20 }
  await evaluate()
  if (!error.value) notice.value = '演示情景已完成真实软件预演。点击“启动任务”开始运行；事件由你操作触发。'
}

async function control(action) {
  await act(async () => {
    try {
      currentRun.value = await api.control(currentRun.value.id, action)
      lastUpdate.value = new Date()
    } catch (cause) {
      if (cause.status === 409) currentRun.value = await api.run(currentRun.value.id)
      throw cause
    }
  })
}

async function sendWind() {
  await act(async () => {
    currentRun.value = await sendCurrentEvent({ type: 'wind', wind: [Number(windX.value), Number(windY.value)] })
    notice.value = '风变化已保存；后端在下一个真实格节点重算路线与预算，暂停时位置保持不变。'
  })
}

async function sendCurrentEvent(payload) {
  try { return await api.event(currentRun.value.id, payload) }
  catch (cause) {
    if (cause.status === 409) currentRun.value = await api.run(currentRun.value.id)
    throw cause
  }
}

async function sendObstacle(cell) {
  if (!addObstacle.value || !controllable.value || busy.value) return
  await act(async () => {
    currentRun.value = await sendCurrentEvent({ type: 'obstacle', cells: [cell] })
    addObstacle.value = false
    notice.value = `新增障碍 [${cell.join(', ')}] 已保存；在下一个真实格节点重算路线与预算。`
  })
}

async function openArchive(id) {
  await act(async () => { archiveRun.value = await api.run(id); viewId.value = id; page.value = 'review' })
}

async function replay() {
  await act(async () => {
    currentRun.value = await api.createRun({ replay_of_run_id: archiveRun.value.id })
    page.value = 'running'
    notice.value = '已创建复演任务，原记录保留。复演沿用原配置和手动事件。'
  })
}

onMounted(async () => {
  try {
    catalog.value = await api.scenarios()
    config.value = { ...config.value, ...catalog.value.defaults }
    await loadHistory()
    const activeRun = history.value.find((item) => item.runtime_available !== false && ['RUNNING', 'PAUSED'].includes(item.status))
    if (activeRun) { currentRun.value = await api.run(activeRun.id); lastUpdate.value = new Date() }
  } catch (cause) { error.value = reasonText(cause.message) }
  finally { loading.value = false }
})
onBeforeUnmount(() => { disposed = true; stopPolling() })
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="#" @click.prevent="page = 'preview'"><span class="brand-symbol">航</span><span><strong>寒域智航</strong><small>巡检任务验证平台</small></span></a>
      <div class="sidebar-scene"><span class="tiny-label">应用场景</span><strong>东北 · 冰雪景区</strong><p>让巡检去得了，也回得来。</p></div>
      <nav aria-label="主导航">
        <button :class="{ selected: page === 'preview' }" @click="page = 'preview'"><span class="nav-number">01</span><span>任务预演</span></button>
        <button :class="{ selected: page === 'running' }" @click="page = 'running'"><span class="nav-number">02</span><span>运行与调整</span><i v-if="running" class="live-dot"></i></button>
        <button :class="{ selected: page === 'review' }" @click="page = 'review'"><span class="nav-number">03</span><span>结果复查</span></button>
      </nav>
      <div class="sidebar-bottom"><span class="small-label">作品边界</span><p>固定高度 · 二维 · 单机<br />三点顺序巡检与返程</p><span class="sidebar-tag">本机确定性软件仿真</span></div>
    </aside>

    <main class="main-content">
      <div class="source-strip"><span><i class="source-dot"></i>LOCAL_2D_SIM</span><span>参数化软件情景 · 非真实低温测量 · 不控制真实飞机</span></div>
      <header class="page-heading"><div><span class="eyebrow">{{ pageMeta[page].eyebrow }}</span><h1>{{ pageMeta[page].title }}</h1><p>{{ pageMeta[page].description }}</p></div><button v-if="page === 'preview'" class="button secondary" :disabled="busy || !catalog" @click="demo">加载 90 秒演示情景</button><button v-else-if="page === 'review'" class="button secondary" :disabled="busy" @click="loadHistory">刷新档案</button></header>
      <div v-if="error" class="message error" role="alert"><strong>操作未完成</strong><span>{{ error }}</span><button aria-label="关闭错误提示" @click="error = ''">×</button></div>
      <div v-if="notice" class="message success" role="status"><span>{{ notice }}</span><button aria-label="关闭提示" @click="notice = ''">×</button></div>
      <div v-if="loading" class="empty-state">正在读取本机情景与参数…</div>

      <template v-else-if="page === 'preview'">
        <div class="preview-layout">
          <section class="panel setup-panel">
            <div class="section-heading"><h2>任务配置</h2><span class="small-label">一架次 · 三个点</span></div>
            <label class="field">任务情景<select v-model="config.scenario_id" :disabled="busy"><option v-for="scene in scenes" :key="scene.id" :value="scene.id">{{ scene.name }}</option></select></label>
            <p class="helper scene-id">情景 {{ config.scenario_id }} · 固定 seed {{ selectedScene?.seed ?? '—' }}</p>
            <div class="field-row"><label class="field">温度情景<select v-model.number="config.temperature_c" :disabled="busy || !temperatures.length"><option v-for="temperature in temperatures" :key="temperature" :value="temperature">{{ temperature }} °C</option><option v-if="!temperatures.length" :value="config.temperature_c">{{ config.temperature_c }} °C · 参数待提供</option></select></label><label class="field">储备比例<select v-model.number="config.reserve_fraction" :disabled="busy"><option :value="0.1">10%</option><option :value="0.2">20%</option><option :value="0.3">30%</option></select></label></div>
            <label class="field">仿真倍速<select v-model.number="config.speedup" :disabled="busy"><option :value="5">5 倍</option><option :value="10">10 倍</option><option :value="20">20 倍 · 演示推荐</option><option :value="40">40 倍</option></select></label>
            <div class="field"><span>运行策略</span><div class="segmented"><button :class="{ chosen: config.strategy === 'distance' }" @click="config.strategy = 'distance'">距离优先</button><button :class="{ chosen: config.strategy === 'energy' }" @click="config.strategy = 'energy'">能量优先</button></div></div>
            <button class="button secondary full-width" :disabled="busy || !selectedScene" @click="evaluate">{{ busy ? '正在计算…' : '比较两种策略' }}</button>
            <button class="button primary full-width" :disabled="busy || !selectedScene || controllable" @click="createRun">启动任务 <span>→</span></button>
            <p v-if="controllable" class="helper">已有未结束任务，请先在“运行与调整”中结束当前任务。</p>
            <details class="parameter-details"><summary>温度参数与适用条件</summary><p :class="{ negative: !parameters.available }">{{ parameters.available ? '后端已提供参数化情景。' : '可用能量参数尚不可用。' }} {{ parameters.reason }}</p><p>厂家参考曲线来自 −20 / 0 / 23 °C。−10 °C 使用相邻温度曲线插值：先在相同放电比例下推算电压，再积分得到 Wh；它不是厂家直接测点。只在 −20 至 23 °C 范围内使用，不做温度外推。</p><p>参考条件：4.2 A 恒流放电、2.5 V 截止、23 °C 充电；理想一致电芯 4S1P 虚拟组。情景假定环境与电芯热平衡，不代表实际无人机电池。</p><pre>{{ sourceText }}</pre><p>情景参数用于软件验证，不能替代真实低温电池标定。储备比例为本作品仿真配置。</p></details>
          </section>
          <div class="preview-main">
            <section class="panel map-panel"><MissionMap :scene="selectedScene" :distance-run="distanceRun" :energy-run="energyRun" /></section>
            <div class="comparison-row">
              <button v-for="[strategy, run] in [['distance', distanceRun], ['energy', energyRun]]" :key="strategy" :class="['strategy-card', { selected: config.strategy === strategy }]" @click="config.strategy = strategy"><div><span :class="['strategy-marker', strategy]"></span><strong>{{ strategyName(strategy) }}</strong><span class="checkmark">{{ config.strategy === strategy ? '已选择' : '选择运行' }}</span></div><p>{{ strategy === 'distance' ? '优先缩短路线，保留返程预算检查。' : '按声明的风场与能量代价规划路线。' }}</p><div class="strategy-stats"><span>仿真耗能 <b>{{ number(run?.summary?.total_energy_wh) }} Wh</b></span><span>巡检完成 <b>{{ percent(run?.summary?.mission_completion_ratio) }}</b></span><span>回收点 <b>{{ run ? (run.summary?.returned ? '已返回' : '未返回') : '待预演' }}</b></span></div></button>
            </div>
            <section class="panel"><EnergyBudget :budget="previewBudget" mode="mission" /><p v-if="evaluation?.comparison" class="comparison-note">{{ reasonText(evaluation.comparison.reason) }}<span v-if="Number.isFinite(evaluation.comparison.energy_saving_pct)"> · 成对仿真耗能差 {{ number(evaluation.comparison.energy_saving_pct) }}%</span></p></section>
          </div>
        </div>
      </template>

      <template v-else-if="page === 'running'">
        <div v-if="!currentRun" class="empty-state"><div class="empty-icon">↗</div><h2>还没有运行任务</h2><p>先选一个情景，核算巡检和返程预算。</p><button class="button primary" @click="page = 'preview'">前往任务预演</button></div>
        <template v-else>
          <div class="run-toolbar"><div><span :class="['badge', currentRun.status.toLowerCase()]">{{ runStatus(currentRun.status) }}</span><strong>{{ scenarioNames[currentRun.scenario_id] || currentRun.scenario_id }}</strong><span>{{ strategyName(currentRun.strategy) }} · {{ currentRun.temperature_c }} °C · {{ currentRun.speedup }} 倍速</span></div><div class="toolbar-actions"><button v-if="running" class="button secondary small" :disabled="busy" @click="control('pause')">暂停</button><button v-if="controllable && currentRun.status === 'PAUSED'" class="button primary small" :disabled="busy" @click="control('resume')">继续</button><button v-if="controllable" class="button quiet small" :disabled="busy" @click="control('cancel')">结束任务</button><button v-else class="button secondary small" :disabled="busy" @click="openArchive(currentRun.id)">查看完整档案</button></div></div>
          <div v-if="!controllable" class="terminal-summary"><strong>{{ oldSession ? '旧会话记录，请在结果复查中复演为新任务。' : (reasonText(currentRun.summary?.ended_reason) || runStatus(currentRun.status)) }}</strong><span>巡检完成 {{ percent(currentRun.summary?.mission_completion_ratio) }} · {{ currentRun.summary?.returned ? '已返回回收点' : '未返回回收点' }}</span></div><div v-if="pollingError" class="message error" role="alert">读取状态失败：{{ pollingError }}。当前画面保留上一次返回值，不推进位置。</div>
          <div class="stats-grid"><div class="stat-card"><span>已巡检</span><strong>{{ currentRun.summary?.visited_count ?? currentRun.visited_targets?.length ?? 0 }}<small> / {{ currentRun.targets?.length || 3 }} 点</small></strong></div><div class="stat-card"><span>剩余可用能量</span><strong>{{ number(telemetry?.remaining_usable_wh ?? currentRun.currentbudget?.available_wh) }}<small> Wh</small></strong></div><div class="stat-card"><span>累计仿真耗能</span><strong>{{ number(telemetry?.discharged_wh ?? currentRun.summary?.total_energy_wh) }}<small> Wh</small></strong></div><div class="stat-card"><span>仿真经过时间</span><strong>{{ number(currentRun.t_s, 1) }}<small> s</small></strong></div></div>
          <div class="running-layout"><div class="running-main"><section class="panel map-panel"><div v-if="addObstacle" class="map-instruction">点击地图中的一个格子，发送新增障碍事件。<button @click="addObstacle = false">取消</button></div><MissionMap :scene="currentRun" :interactive="addObstacle && controllable && !busy" @cell="sendObstacle" /><div class="update-label">位置来自后端 · {{ lastUpdate ? `上次读取 ${lastUpdate.toLocaleTimeString('zh-CN')}` : '等待读取' }} · {{ running ? '200 ms 轮询' : '当前状态不轮询' }}</div></section><section class="panel"><EnergyTrace :telemetry="currentRun.telemetry || []" /></section></div><div class="running-side"><section class="panel"><EnergyBudget :budget="currentRun.currentbudget" :stopped="!controllable" compact /></section><section class="panel event-controls"><div class="section-heading"><h2>条件变化</h2><span class="small-label">手动事件</span></div><p class="helper">操作发送到后端，返回结果后更新地图与判断。</p><div class="field-row"><label class="field">风 x · m/s<input v-model.number="windX" type="number" min="-12" max="12" step="1" /></label><label class="field">风 y · m/s<input v-model.number="windY" type="number" min="-12" max="12" step="1" /></label></div><button class="button secondary full-width" :disabled="busy || !controllable" @click="sendWind">发送风变化</button><button :class="['button', 'full-width', addObstacle ? 'primary' : 'secondary']" :disabled="busy || !controllable" @click="addObstacle = !addObstacle">{{ addObstacle ? '正在选择障碍位置…' : '在地图上新增障碍' }}</button><p v-if="!controllable" class="helper">{{ oldSession ? '旧会话无法恢复控制，请复演创建新任务。' : '任务已结束，条件变化按钮不可用。' }}</p></section></div></div>
          <section class="panel decision-panel"><div class="section-heading"><h2>判断时间线</h2><span class="small-label">{{ currentRun.decisions?.length || 0 }} 条决策 · {{ currentRun.events?.length || 0 }} 个事件</span></div><div v-if="!currentRun.decisions?.length" class="empty-inline">后端尚未返回决策。</div><div v-for="(decision, index) in [...(currentRun.decisions || [])].reverse().slice(0, 6)" :key="index" class="decision-row"><time>{{ number(decision.t_s, 1) }} s</time><div><strong>{{ decisionLabels[decision.decision] || decision.decision }}</strong><p>{{ reasonText(decision.reason) }}</p></div></div></section>
          <p class="archive-id">运行 ID：{{ currentRun.id }}</p>
        </template>
      </template>

      <template v-else-if="page === 'review'">
        <div class="review-layout"><section class="panel archive-list"><div class="section-heading"><h2>任务档案</h2><span class="small-label">{{ history.length }} 条记录</span></div><div v-if="!history.length" class="empty-inline">尚无任务档案。完成预演或启动任务后，可在此复查。</div><button v-for="run in history" :key="run.id" :class="['archive-card', { selected: archiveRun?.id === run.id }]" :disabled="busy" @click="openArchive(run.id)"><div><strong>{{ scenarioNames[run.scenario_id] || run.scenario_id }}</strong><span :class="['badge', run.status.toLowerCase()]">{{ runStatus(run.status) }}</span></div><p>{{ strategyName(run.strategy) }} · {{ run.temperature_c }} °C · {{ number(run.summary?.total_energy_wh) }} Wh</p><small>{{ run.id }}</small></button></section><div class="archive-detail"><div v-if="!archiveRun" class="panel empty-state"><div class="empty-icon">▤</div><h2>选择一次任务</h2><p>查看它的配置、路线、决策与事件。</p></div><template v-else><section class="panel"><div class="section-heading"><div><h2>{{ scenarioNames[archiveRun.scenario_id] || archiveRun.scenario_id }}</h2><p class="helper">{{ strategyName(archiveRun.strategy) }} · {{ archiveRun.temperature_c }} °C · {{ runStatus(archiveRun.status) }}</p></div><div class="toolbar-actions"><a class="button secondary small" :href="api.exportUrl(archiveRun.id)" :download="`${archiveRun.id}.json`">导出 JSON</a><button class="button primary small" :disabled="busy || controllable" @click="replay">复演为新任务</button></div></div><div class="detail-stats"><span>巡检完成 <b>{{ percent(archiveRun.summary?.mission_completion_ratio) }}</b></span><span>返回回收点 <b>{{ archiveRun.summary?.returned ? '是' : '否' }}</b></span><span>仿真耗能 <b>{{ number(archiveRun.summary?.total_energy_wh) }} Wh</b></span><span>结束原因 <b>{{ reasonText(archiveRun.summary?.ended_reason) || '尚未结束' }}</b></span></div><p v-if="archiveRun.runtime_available === false && ['RUNNING', 'PAUSED'].includes(archiveRun.status)" class="old-session-hint">旧会话记录，当前服务无法继续控制。点击“复演为新任务”沿用原配置与事件。</p><p class="archive-id">{{ archiveRun.id }}</p></section><section class="panel map-panel"><MissionMap :scene="archiveRun" /></section><section class="panel"><EnergyTrace :telemetry="archiveRun.telemetry || []" /></section><section class="panel"><div class="section-heading"><h2>决策记录</h2><span class="small-label">原记录保留</span></div><div v-for="(decision, index) in archiveRun.decisions || []" :key="index" class="decision-row"><time>{{ number(decision.t_s, 1) }} s</time><div><strong>{{ decisionLabels[decision.decision] || decision.decision }}</strong><p>{{ reasonText(decision.reason) }}</p></div></div><p v-if="!archiveRun.decisions?.length" class="empty-inline">没有决策记录。</p></section><section class="panel"><div class="section-heading"><h2>条件变化记录</h2><span class="small-label">按后端保存结果显示</span></div><div class="table-wrap"><table><thead><tr><th>仿真时间</th><th>事件</th><th>来源</th><th>参数</th><th>已应用</th></tr></thead><tbody><tr v-for="event in archiveRun.events || []" :key="event.event_id"><td>{{ number(event.t_s, 1) }} s</td><td>{{ event.type === 'wind' ? '风变化' : event.type === 'obstacle' ? '新增障碍' : event.type }}</td><td>{{ event.source === 'manual' ? '手动' : '情景预置' }}</td><td><code>{{ JSON.stringify(event.payload) }}</code></td><td>{{ event.applied ? '是' : '否' }}</td></tr></tbody></table></div><p v-if="!archiveRun.events?.length" class="empty-inline">没有条件变化事件。</p></section></template></div></div>
      </template>

      <footer class="page-footer"><span>能量单位 Wh · 任务判断仅在声明的仿真条件下成立</span><span>现有 LSTM 模型研究独立保存，本任务未接入 LSTM 推理</span></footer>
    </main>
  </div>
</template>
