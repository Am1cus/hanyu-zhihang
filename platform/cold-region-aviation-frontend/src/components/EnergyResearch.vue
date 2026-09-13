<template>
  <section class="research-workspace">
    <section class="panel comparison-workspace">
      <div class="run-picker">
        <label>选择一条V3记录<el-select v-model="selectedId" aria-label="V3实验选择" placeholder="暂无V3记录" @change="selectRun"><el-option v-for="run in runs" :key="run.runId" :value="run.runId" :label="run.flightId+' · '+shortDate(run.createdAt)+' · '+run.runId.slice(0,8)" /></el-select></label>
        <el-button :loading="loading" @click="load">刷新记录</el-button><router-link v-if="selectedRun" :to="{path:'/dashboard',query:{runId:selectedId}}">在看板中查看 →</router-link>
      </div>
      <div v-if="runError" class="notice error" role="alert">{{ runError }}</div>
      <div v-if="!runs.length && !loading && !runError" class="empty"><h3>还没有V3记录</h3><p>先按使用指南回放新AirSim数据包，或到预测看板查看已有的其他版本记录。</p><router-link to="/dashboard">前往预测看板 →</router-link></div>
      <div v-if="runLoading" class="empty" role="status">正在读取这一条记录，图表不会借用其他架次。</div>
      <template v-if="selectedRun">
        <p class="run-label"><span class="pill idle">{{ evaluationLabel(selectedRun.configuration?.evaluation_role) }}</span><span>{{ selectedRun.sampleCount }}条 · {{ selectedRun.status==='COMPLETED' ? '已完成' : '未完成' }}</span></p>
        <p v-if="selectedRun.configuration?.engineering_test" class="run-label">工程回放检查，不增加独立数据量。</p>
        <div class="method-cards">
          <div v-for="(method,index) in methods" :key="method.name" :class="{candidate:index===0}"><span>{{ method.name }}</span><strong>{{ format(method.mape,2) }}<small>%</small></strong><p>平均相对误差 · {{ method.count }} 个相同片段</p></div>
        </div>
        <p class="comparison-conclusion">{{ comparisonSummary(methods) }}</p>
        <p class="comparison-boundary">这只说明本次记录的效果。当前数据已参与探索性选型或尚未完成确认，不代表新的独立验证、真实低温电池或航程达标。</p>
        <div class="panel-head"><div><h2>三种方法，和实际耗电一起看</h2><p>绿色为仿真实际值；橙色为LSTM预测；点线为两种简单估算。</p></div></div>
        <ForecastChart :rows="rows" baselines />
        <p class="chart-caption">纵轴放大局部差异，不从零开始。曲线没有平滑或线性修正，末尾缺少实际值的预测不计误差。</p>
        <details class="metrics-detail"><summary>误差指标与两种简单方法的含义</summary>
          <div class="readable-table"><table><thead><tr><th>方法</th><th>相对误差 MAPE ↓</th><th>平均差值 MAE ↓</th><th>共同片段</th></tr></thead><tbody><tr v-for="method in methods" :key="method.name"><th>{{ method.name }}</th><td>{{ format(method.mape,3) }} %</td><td>{{ format(method.mae,3) }} mAh</td><td>{{ method.count }}</td></tr></tbody></table></div>
          <p>历史耗电延续：假设未来10秒与过去10秒耗电相同。均流估算：假设接下来保持过去20秒的平均电流。这两种方法不使用LSTM。</p><p>MAPE是各片段相对误差的平均值，MAE是耗电差值的平均值。二者越小越好，不等于“100%减误差”的准确率。表格来自完整存档，曲线最多显示最近1800条。</p>
        </details>
      </template>
    </section>
    <details class="disclosure candidate-details">
      <summary>候选模型说明、限制与下载</summary>
      <div v-if="error" class="notice error" role="status">{{ error }} 历史记录不受影响。</div>
      <template v-if="report">
        <p>运动特征残差LSTM：{{ report.manifest.architecture.hidden_size }}单元 × {{ report.manifest.architecture.layers }}层，{{ report.manifest.architecture.members }}个{{ report.manifest.architecture.precision }}成员。温度没有直接作为输入，低温可用能量模块尚待开发。</p>
        <p>冻结运行时已复算{{ report.offline_recheck.windows_reproduced }}个原有窗口；这是可复现性证据，不是新的准确率验证。</p>
        <p>原开发集选择的{{ report.manifest.original_preselected_candidate }}未通过推广门槛；当前残差候选是在查看结果后选定，需要新数据确认。</p>
        <p>模型：<code>{{ report.manifest.model_version }}</code></p><p>清单SHA-256：<code>{{ report.manifest_sha256 }}</code></p>
        <el-button :disabled="!!error" @click="downloadJson(report,'energy-v3-candidate-report.json')">下载候选模型说明</el-button>
      </template>
    </details>
    <p class="footnote">优先展示最近完整完成的普通记录；没有符合条件的记录时展示最新记录，请留意其状态与用途。不按模型分数挑选。下拉列表读取最近100次运行；更早记录可从预测看板的「切换记录」打开。</p>
  </section>
</template>
<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getEnergyV3Report } from '@/api/demo'
import { listRuns, getRun, getRunEvents } from '@/api/runs'
import { format, evaluationLabel, downloadJson } from '@/utils/telemetry'
import { defaultResearchRun, shortDate, comparisonSummary } from '@/utils/presentation'
import ForecastChart from './ForecastChart.vue'
const route=useRoute(), router=useRouter()
const loading=ref(false), error=ref(''), report=ref(null), runs=ref([]), selectedId=ref(null)
const selectedRun=ref(null), rows=ref([]), runLoading=ref(false), runError=ref('')
let loadVersion=0, runVersion=0
const methods=computed(() => [['lstm','LSTM候选'],['history_10s','历史耗电延续'],['mean_current_20s','20秒均流估算']].map(([key,name]) => {
  const metric=selectedRun.value?.baselineMetrics?.[key] || {}
  return {name,count:metric.count || 0,mae:metric.mae_mah,mape:metric.mape_pct}
}))
async function load() {
  const version=++loadVersion
  loading.value=true;error.value='';runError.value=''
  try {
    const [model,archive]=await Promise.allSettled([getEnergyV3Report(),listRuns({page:1,size:100})])
    if(version!==loadVersion) return
    if(model.status==='fulfilled' && model.value.data?.manifest) report.value=model.value.data
    else {report.value=null;error.value='模型说明暂不可用。'}
    if(archive.status!=='fulfilled') throw new Error('档案读取失败')
    runs.value=(archive.value.data.records || []).filter(r=>r.configuration?.execution_mode==='research_shadow')
    const requested=typeof route.query.runId==='string' ? route.query.runId : null
    selectedId.value=requested || (runs.value.some(r=>r.runId===selectedId.value) ? selectedId.value : defaultResearchRun(runs.value)?.runId) || null
    if(selectedId.value) await loadRun()
    else {selectedRun.value=null;rows.value=[]}
  } catch {if(version===loadVersion) runError.value='无法读取实验记录，请确认后台在线后刷新。'}
  finally {if(version===loadVersion) loading.value=false}
}
function selectRun(id) {router.replace({path:'/experiments',query:{runId:id}})}
watch(()=>route.query.runId, id=>{if(typeof id==='string'){selectedId.value=id;loadRun()}})
async function loadRun() {
  const id=selectedId.value, version=++runVersion
  rows.value=[];selectedRun.value=null;runError.value='';runLoading.value=true
  try {
    const detail=(await getRun(id)).data
    if(detail.configuration?.execution_mode!=='research_shadow') throw new Error('not_v3')
    let after=Math.max(-1,(detail.metrics?.last_sample_seq ?? detail.sampleCount-1)-1800), events=[]
    for(let page=0;page<2;page++){
      const limit=page===0?1000:800, chunk=(await getRunEvents(id,after,limit)).data || []
      events.push(...chunk)
      if(chunk.length<limit) break
      after=chunk.at(-1).telemetry.sampleSeq
    }
    if(version!==runVersion) return
    rows.value=events.map(e=>({...e.telemetry,prediction:e.prediction,verification:e.verification}))
    selectedRun.value=detail
    if(!runs.value.some(r=>r.runId===id)) runs.value=[detail,...runs.value]
  } catch(cause){if(version===runVersion) runError.value=cause.message==='not_v3'?'这条记录使用旧模型，请查看下方旧版V2报告，或返回预测看板。':'这条记录读取失败，没有用其他架次替代。'}
  finally{if(version===runVersion) runLoading.value=false}
}
onMounted(load)
</script>
<style scoped>
.research-workspace{margin-bottom:24px}.comparison-workspace>.notice{margin:16px 24px}.run-picker{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;padding:20px 24px}.run-picker label{display:grid;gap:8px;flex:1;min-width:240px;font-size:.875rem;color:var(--muted)}.run-picker .el-select{width:100%}.run-picker a{font-size:.875rem;min-height:40px;display:flex;align-items:center}.run-label{display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:.8125rem;color:var(--muted);padding:0 24px 16px;line-height:1.7}
.method-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:0 24px}.method-cards>div{border:1px solid var(--line);border-radius:8px;padding:16px}.method-cards .candidate{border-top:3px solid var(--green);padding-top:14px;background:#f6faf7}.method-cards span{font-size:.875rem}.method-cards strong{display:block;font-size:1.875rem;margin:8px 0;color:var(--ink);font-variant-numeric:tabular-nums}.method-cards small{font-size:.875rem;font-weight:400;margin-left:5px}.method-cards p{font-size:.8125rem;color:var(--muted);line-height:1.6}
.comparison-conclusion{font-size:1rem;font-weight:550;padding:18px 24px 4px;line-height:1.7}.comparison-boundary{padding:0 24px 10px;font-size:.8125rem;color:var(--muted);line-height:1.7}.chart-caption{padding:8px 24px 18px;font-size:.8125rem;color:var(--muted);line-height:1.7}.metrics-detail{padding:18px 24px;border-top:1px solid var(--line)}.metrics-detail p,.candidate-details p{font-size:.875rem;color:var(--muted);line-height:1.8;margin:14px 0;overflow-wrap:anywhere}.readable-table{overflow-x:auto;margin-top:16px}table{border-collapse:collapse;width:100%;min-width:600px;font-size:.875rem;text-align:left}th,td{padding:12px;border-bottom:1px solid var(--line)}thead{background:#f3f6f5}th{font-weight:550}.candidate-details{margin:18px 0}
@media(max-width:760px){.run-picker{padding:18px 16px;gap:10px}.run-picker label{flex-basis:100%;min-width:0}.run-label{padding:0 16px 14px}.method-cards{grid-template-columns:1fr;padding:0 16px;gap:8px}.method-cards>div{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:12px 14px}.method-cards .candidate{padding:10px 14px 12px}.method-cards strong{font-size:1.5rem;margin:0;grid-column:2;grid-row:1/3;align-self:center}.method-cards p{grid-column:1}.comparison-conclusion,.comparison-boundary,.chart-caption,.metrics-detail{padding-left:16px;padding-right:16px}}
</style>
