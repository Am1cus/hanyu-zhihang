<template>
  <section class="research-workspace">
    <div class="research-title"><div><span class="eyebrow">Frozen candidate / V3</span><h2>运动特征残差 LSTM</h2><p>30秒输入 · 未来10秒耗电 · 候选旁路运行</p></div><div class="actions"><el-button :disabled="!report || !!error" @click="downloadJson(report,'energy-v3-candidate-report.json')">下载候选模型说明</el-button><el-button :loading="loading" @click="load">刷新模型与档案</el-button></div></div>
    <div v-if="error" class="notice error">{{ error }}</div>
    <div class="notice">已完成探索性选型，尚待独立确认。当前为 AirSim 运动学＋公式电池，不能据此宣称低温真机航程、SOH或自动返航已经达标。</div>
    <section v-if="report" class="panel candidate-facts">
      <div><span>结构</span><strong>{{ report.manifest.architecture.hidden_size }}单元 × {{ report.manifest.architecture.layers }}层</strong></div>
      <div><span>集成成员 / 精度</span><strong>{{ report.manifest.architecture.members }} / {{ report.manifest.architecture.precision }}</strong></div>
      <div><span>冻结运行时复算</span><strong>{{ report.offline_recheck.windows_reproduced }}窗口</strong><small>复算一致不等于独立验证</small></div>
      <details><summary>模型身份与边界</summary><p class="mono">{{ report.manifest.model_version }}</p><p>原始开发集选定方法：{{ report.manifest.original_preselected_candidate }}；原推广门槛未通过。当前残差候选是在查看固定实验结果后选出，需要新数据确认。</p><p class="mono">清单SHA-256：{{ report.manifest_sha256 }}</p><p>温度没有直接作为V3输入；低温可用能量模块尚待开发。</p></details>
    </section>
    <section class="panel run-panel">
      <div class="panel-head"><div><h2>选择已保存的 V3 实验</h2><p>从最近100次运行中读取V3档案；更早记录可在飞行监测的历史实验中查询。</p></div></div>
      <div class="run-picker"><el-select v-model="selectedId" placeholder="先回放一个 V3 架次" aria-label="V3实验选择" @change="loadRun"><el-option v-for="run in runs" :key="run.runId" :value="run.runId" :label="run.flightId + ' · ' + run.runId.slice(0,8) + ' · ' + evaluationLabel(run.configuration?.evaluation_role)" /></el-select><router-link v-if="selectedId" :to="{path:'/dashboard',query:{runId:selectedId}}">打开完整回放记录 →</router-link></div>
      <div v-if="!runs.length && !loading" class="empty"><h3>尚无 V3 回放档案</h3><p>在飞行监测页查看回放说明；新数据包会显式选择候选模型。</p></div>
      <div v-if="runError" class="notice error">{{ runError }}</div>
      <template v-if="selectedRun">
        <p class="run-label">{{ selectedRun.flightId }} · {{ evaluationLabel(selectedRun.configuration?.evaluation_role) }} · {{ selectedRun.sampleCount }}条 / {{ selectedRun.status === 'COMPLETED' ? '已完成' : '未完成' }}</p>
        <p v-if="selectedRun.configuration?.engineering_test" class="run-label">本条为工程回放检查，不增加独立数据量：{{ selectedRun.configuration.engineering_test }}</p>
        <ForecastChart :rows="rows" baselines />
        <p class="run-label">纵轴为局部范围，不从零开始；四条曲线没有平滑、加噪或线性纠正。末尾缺未来标签不计误差。</p>
        <el-table :data="methods" v-loading="runLoading">
          <el-table-column prop="name" label="方法" min-width="220" />
          <el-table-column prop="count" label="共同有效窗口" min-width="130" />
          <el-table-column label="耗电 MAPE ↓" min-width="140"><template #default="{row}">{{ format(row.mape,3) }} %</template></el-table-column>
          <el-table-column label="MAE ↓" min-width="120"><template #default="{row}">{{ format(row.mae,3) }} mAh</template></el-table-column>
        </el-table>
        <p class="run-label">表格指标来自后台完整存档；图表显示最近1800条。单架次结果与重复回放不构成独立模型确认。</p>
      </template>
    </section>
  </section>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { getEnergyV3Report } from '@/api/demo'
import { listRuns, getRun, getRunEvents } from '@/api/runs'
import { format, evaluationLabel, downloadJson } from '@/utils/telemetry'
import ForecastChart from './ForecastChart.vue'
const loading=ref(false), error=ref(''), report=ref(null), runs=ref([]), selectedId=ref(null)
const selectedRun=ref(null), rows=ref([]), runLoading=ref(false), runError=ref('')
let loadVersion=0, runVersion=0
const methods=computed(() => [['lstm','LSTM V3候选'],['history_10s','延续过去10秒耗电'],['mean_current_20s','过去20秒均流估算']].map(([key,name]) => {
  const metric=selectedRun.value?.baselineMetrics?.[key] || {}
  return {name,count:metric.count || 0,mae:metric.mae_mah,mape:metric.mape_pct}
}))
async function load() {
  const version=++loadVersion
  loading.value=true;error.value=''
  try {
    const [model,archive]=await Promise.all([getEnergyV3Report(),listRuns({page:1,size:100})])
    if(version!==loadVersion) return
    if(model.data?.manifest) report.value=model.data
    else { report.value=null;error.value='V3模型报告暂不可用；历史档案仍可查看。' }
    runs.value=(archive.data.records || []).filter(r => r.configuration?.execution_mode==='research_shadow')
    if(!runs.value.some(r=>r.runId===selectedId.value)) selectedId.value=runs.value[0]?.runId || null
    if(selectedId.value) await loadRun()
  } catch { if(version===loadVersion) error.value='读取失败，请确认后台和AI在线后重试。' }
  finally { if(version===loadVersion) loading.value=false }
}
async function loadRun() {
  const id=selectedId.value, version=++runVersion
  rows.value=[];selectedRun.value=null;runError.value='';runLoading.value=true
  try {
    const detail=(await getRun(id)).data
    let after=Math.max(-1,(detail.metrics?.last_sample_seq ?? detail.sampleCount-1)-1800), events=[]
    for(let page=0;page<2;page++) {
      const limit=page===0?1000:800, chunk=(await getRunEvents(id,after,limit)).data || []
      events.push(...chunk)
      if(chunk.length<limit) break
      after=chunk.at(-1).telemetry.sampleSeq
    }
    if(version!==runVersion) return
    rows.value=events.map(e=>({...e.telemetry,prediction:e.prediction,verification:e.verification}))
    selectedRun.value=detail
  } catch { if(version===runVersion) runError.value='该次实验读取失败，没有用其他实验替代。' }
  finally { if(version===runVersion) runLoading.value=false }
}
onMounted(load)
</script>
<style scoped>
.research-workspace{margin-bottom:30px}.research-title{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:18px}.research-title h2{font-size:25px;font-weight:550;margin:8px 0}.research-title p,.run-label{font-size:14px;color:var(--muted);line-height:1.8}.candidate-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:22px;margin:18px 0}.candidate-facts span,.candidate-facts small{display:block;color:var(--muted);font-size:14px}.candidate-facts strong{display:block;margin:10px 0;font-size:23px;font-weight:500}.candidate-facts details{grid-column:1/-1;font-size:14px;line-height:1.8;overflow-wrap:anywhere}.candidate-facts summary{cursor:pointer}.candidate-facts p{margin-top:10px}.run-picker{display:flex;align-items:center;gap:18px;padding:0 22px 10px}.run-picker .el-select{width:min(650px,100%)}.run-picker a{font-size:14px;white-space:nowrap}.run-label{padding:8px 22px}.run-panel{padding-bottom:15px;overflow:hidden}.mono{font-size:12px}@media(max-width:760px){.research-title,.run-picker{flex-wrap:wrap}.candidate-facts{grid-template-columns:1fr}.candidate-facts strong{font-size:20px}}
</style>
