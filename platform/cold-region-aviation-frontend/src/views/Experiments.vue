<template>
  <div>
    <div class="page-heading">
      <div><div class="eyebrow">Model evaluation / 02</div><h1>实验验证</h1><p>把模型能做什么、效果如何、尚未证明什么放在一起。</p></div>
      <div class="actions"><el-button :icon="Refresh" :loading="loading" @click="loadReport">读取旧版V2报告</el-button><el-button :icon="Download" :disabled="!report || !!error" @click="downloadJson(report, 'airsim-capacity-validation-v2.json')">下载旧版V2报告</el-button></div>
    </div>
    <EnergyResearch />
    <details class="legacy-report"><summary>旧版 V2 离线报告与历史研究结论（保留，不代表 V3）</summary>
    <div v-if="error" class="notice error">{{ error }} <span v-if="report">下方为上次成功读取的报告。</span></div>
    <div v-if="!report" class="panel empty"><h3>{{ loading ? '正在读取模型报告' : '暂无可用报告' }}</h3><p>报告由后台读取 AI 服务中的版本化验证文件，不使用前端固定分数。</p></div>
    <template v-else>
      <section class="experiment-banner">
        <div><span class="eyebrow">Current model</span><h2>短时耗电量预测 <span>V2</span></h2><p class="mono">{{ report.model_version }}</p></div>
        <div class="banner-facts"><span><b>{{ report.lookback_seconds }}</b>秒输入</span><span><b>{{ report.forecast_horizon_seconds }}</b>秒预测</span><span><b>{{ report.features?.length }}</b>维特征</span><span><b>INT8</b>动态量化</span></div>
      </section>

      <div class="experiment-columns">
        <section class="panel">
          <div class="panel-head"><div><h2>独立测试集表现</h2><p>预测目标：未来10秒耗电量。误差越低越好。</p></div><span class="pill idle">离线实验</span></div>
          <div class="test-metrics">
            <div><span>MAPE · 相对误差</span><strong>{{ format(consumption.mape_pct, 2) }}<small>%</small></strong></div>
            <div><span>MAE · 平均绝对误差</span><strong>{{ format(numeric(consumption.mae_ah) === null ? null : consumption.mae_ah * 1000, 3) }}<small>mAh</small></strong></div>
            <div><span>R² · 决定系数</span><strong>{{ format(consumption.r2, 3) }}</strong></div>
          </div>
          <div class="panel-body"><div class="notice">未来“剩余总容量”的 MAPE 为 {{ format(report.quantized_test_metrics?.mape_pct, 3) }}%，但它由当前实测容量减去预测耗电量得到。不能把这个很小的误差解释为模型有“99.9%准确率”。</div></div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>数据与划分</h2><span class="muted" style="font-size:11px">按完整架次隔离</span></div>
          <div class="panel-body">
            <div class="split-bar"><span class="train" :style="{ flex: report.train_flights.length }">{{ report.train_flights.length }}</span><span class="validation" :style="{ flex: report.validation_flights.length }">{{ report.validation_flights.length }}</span><span class="test" :style="{ flex: report.test_flights.length }">{{ report.test_flights.length }}</span></div>
            <div class="split-legend"><span>训练 {{ report.train_flights.length }} 架次</span><span>验证 {{ report.validation_flights.length }} 架次</span><span>测试 {{ report.test_flights.length }} 架次</span></div>
            <p class="data-detail">共 {{ totalFlights }} 架次，其中 {{ report.excluded_short_flights.length }} 架次过短，无法构造完整训练样本。测试集共 {{ report.sample_counts.test }} 个重叠窗口，<strong>不是 {{ report.sample_counts.test }} 次独立飞行</strong>。</p>
            <details><summary>查看测试架次与排除项</summary><p class="mono">测试：{{ report.test_flights.join('、') }}</p><p class="mono">过短：{{ report.excluded_short_flights.join('、') }}</p></details>
          </div>
        </section>
      </div>

      <section class="panel baseline-panel">
        <div class="panel-head"><div><h2>和简单方法相比，模型有优势吗？</h2><p>同样的5个测试架次、105个窗口，不重新拟合，不修改原始预测。</p></div><span class="pill warn">需要继续验证</span></div>
        <div class="panel-body">
          <el-table :data="report.baseline_comparison?.methods || []" empty-text="未读取到基线对照报告">
            <el-table-column prop="name" label="预测方法" min-width="210" />
            <el-table-column label="耗电量 MAPE ↓" min-width="150"><template #default="{ row }"><span :class="{ 'best-score': row.id === bestMethod }">{{ format(row.mape_pct, 3) }} %</span></template></el-table-column>
            <el-table-column label="MAE ↓" min-width="130"><template #default="{ row }">{{ format(row.mae_ah * 1000, 3) }} mAh</template></el-table-column>
            <el-table-column label="结果说明" min-width="200"><template #default="{ row }">{{ row.id === bestMethod ? '本次对照误差最低' : row.id === 'lstm_int8' ? '现有已部署模型' : '电流保持不变的估算' }}</template></el-table-column>
          </el-table>
          <p v-if="report.baseline_comparison" class="conclusion">当前 LSTM 尚未超过“延续过去10秒耗电”的基线。现阶段结论是<strong>推理链路可行，但算法优势尚未成立</strong>；不能只凭曲线接近，就宣称已解决寒区续航问题。</p>
        </div>
      </section>

      <div class="experiment-columns">
        <section class="panel">
          <div class="panel-head"><h2>已经实现的部分</h2></div>
          <div class="panel-body evidence-list">
            <div><span class="check">✓</span><div><h3>仿真数据到网页的推理链路</h3><p>AirSim回放 → 后台保存 → FastAPI LSTM推理 → WebSocket展示。</p></div></div>
            <div><span class="check">✓</span><div><h3>独立架次训练与量化模型</h3><p>V1保留；V2预测10秒耗电，前端不做曲线平滑或线性校正。</p></div></div>
            <div><span class="check">✓</span><div><h3>可追溯的回放核对</h3><p>按时间匹配真实容量；查看到期误差、导出记录、查询并处理规则预警。</p></div></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>下一步的实验顺序</h2></div>
          <div class="panel-body roadmap">
            <div><span>01</span><div><h3>补变化，而不是只补数量</h3><p>采集爬升、悬停、加速、载荷切换与风速变化；增加更长的完整飞行。</p></div></div>
            <div><span>02</span><div><h3>先证明模型超过基线</h3><p>按工况、架次分别评估，与历史耗电外推和电流积分对照，再决定是否调整模型。</p></div></div>
            <div><span>03</span><div><h3>真机验证后，再谈航时与调度</h3><p>校准传感器及容量标签；完成真机误差评估，再扩展剩余航时和路径规划。</p></div></div>
          </div>
        </section>
      </div>
      <div class="notice boundary-note"><strong>研究边界：</strong>当前数据为 AirSim 仿真；尚未完成真机极寒验证。NASA V1容量模型仍保留，但其温度、风速等特征为合成值，不作为极寒实飞证据。SOH评估、改进A*和剩余航时预测均未在本工作台中作为已完成能力展示。</div>
      <p class="footnote report-origin">来源：模型目录中的 airsim_capacity_validation_v2.json 与 capacity_baselines_v2.json · 最近读取 {{ loadedAt || '—' }}</p>
    </template>
    </details>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import EnergyResearch from '@/components/EnergyResearch.vue'
import { Refresh, Download } from '@element-plus/icons-vue'
import { getModelReport } from '@/api/demo'
import { numeric, format, downloadJson } from '@/utils/telemetry'
const report = ref(null), loading = ref(false), error = ref(''), loadedAt = ref('')
const consumption = computed(() => report.value?.quantized_consumption_metrics || {})
const totalFlights = computed(() => ['train_flights', 'validation_flights', 'test_flights', 'excluded_short_flights'].reduce((sum, key) => sum + (report.value?.[key]?.length || 0), 0))
const bestMethod = computed(() => [...(report.value?.baseline_comparison?.methods || [])].sort((a,b) => a.mape_pct - b.mape_pct)[0]?.id)
async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const response = await getModelReport()
    if (response.data?.unavailable || !response.data?.quantized_consumption_metrics) throw new Error('模型报告不可用')
    report.value = response.data
    loadedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
  } catch { error.value = '无法读取模型报告，请确认后台和 AI 服务在线后重试。' }
  finally { loading.value = false }
}
onMounted(loadReport)
</script>
<style scoped>
.legacy-report>summary{font-size:14px;padding:18px 0;cursor:pointer;color:var(--muted)}
.experiment-banner{display:flex;align-items:center;justify-content:space-between;gap:24px;background:#e9eee1;border:1px solid #dbe3d0;border-radius:10px;padding:25px 28px;margin-bottom:20px}.experiment-banner h2{font-size:24px;font-weight:500;margin:6px 0 10px}.experiment-banner h2 span{font-size:12px;background:#d7e3cd;padding:4px 6px;border-radius:4px;vertical-align:middle;margin-left:6px}.experiment-banner p{font-size:11px;color:#77836c}.banner-facts{display:flex;gap:27px}.banner-facts span{font-size:11px;color:#79866e}.banner-facts b{display:block;font-size:24px;font-weight:500;color:#46603b;margin-bottom:6px}.experiment-columns{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}.test-metrics{display:grid;grid-template-columns:1.1fr 1.25fr .8fr;padding:8px 23px 23px;gap:15px}.test-metrics span{font-size:10px;color:var(--muted)}.test-metrics strong{display:block;font-size:31px;font-weight:500;margin-top:12px;font-variant-numeric:tabular-nums}.test-metrics small{font-size:11px;font-weight:400;color:var(--muted);margin-left:5px}.split-bar{display:flex;height:33px;border-radius:5px;overflow:hidden;margin:12px 0}.split-bar span{display:flex;align-items:center;justify-content:center;font-size:11px}.train{background:#647f54;color:white}.validation{background:#b4c5a6;color:#4c6240}.test{background:#e0e7d7;color:#6a7b5e}.split-legend{display:flex;justify-content:space-between;font-size:10px;color:var(--muted)}.data-detail{font-size:12px;color:var(--muted);line-height:1.9;margin:23px 0 12px}.data-detail strong{font-weight:500;color:#626e57}details{font-size:11px;color:#78866a;line-height:1.8}summary{cursor:pointer;color:var(--green)}details p{font-size:10px;margin-top:9px;overflow-wrap:anywhere}.baseline-panel{margin-bottom:20px}.conclusion{font-size:12px;color:#787b6c;background:#f7f5ec;border-left:3px solid #b79664;padding:14px 16px;line-height:1.9;margin-top:20px}.conclusion strong{font-weight:600;color:#6b684f}.best-score{color:#39634d;font-weight:600}.evidence-list>div,.roadmap>div{display:flex;gap:14px;margin:5px 0 23px}.evidence-list>div:last-child,.roadmap>div:last-child{margin-bottom:0}.check{color:#5d7850;background:#ecf2e6;width:20px;height:20px;flex-shrink:0;border-radius:50%;text-align:center;line-height:20px}.evidence-list h3,.roadmap h3{font-size:13px;font-weight:500;margin-bottom:6px}.evidence-list p,.roadmap p{font-size:12px;color:var(--muted);line-height:1.8}.roadmap>div>span{font-family:monospace;font-size:13px;color:#89967a;padding-top:1px}.report-origin{font-size:10px;margin-top:14px;overflow-wrap:anywhere}.boundary-note strong{font-weight:500}
@media(max-width:1100px){.experiment-columns{grid-template-columns:1fr}.experiment-banner{flex-wrap:wrap}.banner-facts{gap:35px}.test-metrics strong{font-size:28px}}
@media(max-width:760px){.experiment-banner{padding:22px}.banner-facts{gap:22px;flex-wrap:wrap}.banner-facts b{font-size:21px}.test-metrics{padding:0 17px 20px;gap:8px}.test-metrics strong{font-size:23px}.test-metrics span{font-size:9px}}
</style>
