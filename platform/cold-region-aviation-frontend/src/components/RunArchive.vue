<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="选择一条实验记录" width="min(920px, 94vw)" @open="load">
    <p class="footnote">打开已保存的曲线，不会重新训练或覆盖记录。相同架次可有多次回放，请留意时间。</p>
    <form class="archive-search" @submit.prevent="page=1; load()"><el-input v-model="flightId" placeholder="输入完整架次，如 F022 或 flight_036" clearable aria-label="架次筛选" /><el-button type="primary" native-type="submit" :loading="loading">查询记录</el-button></form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-loading="loading" class="archive-list">
      <p v-if="!records.length && !loading" class="empty">没有找到记录。可清空筛选重新查询，或按使用指南完成一次回放。</p>
      <article v-for="row in records" :key="row.runId" class="archive-card">
        <div class="archive-title"><h3>{{ row.flightId }}</h3><span class="pill" :class="{idle:row.status!=='COMPLETED'}">{{ statuses[row.status] || row.status }}</span><time>{{ shortDate(row.createdAt) }}</time></div>
        <p class="archive-role">{{ evaluationLabel(row.configuration?.evaluation_role || 'legacy_V2') }}<span v-if="row.configuration?.engineering_test"> · 工程回放检查</span></p>
        <div class="archive-bottom"><p>{{ row.sampleCount }} / {{ row.expectedSamples }} 条数据 · {{ row.metrics?.verified_count || 0 }} 个片段已核对<br><span>平均相对误差 {{ format(row.metrics?.mape_pct,2) }} %</span></p><el-button type="primary" plain @click="open(row.runId)">打开记录</el-button></div>
        <details><summary>记录编号与数据来源</summary><p><code>{{ row.runId }}</code></p><p>{{ row.sourceLabel }}</p></details>
      </article>
    </div>
    <el-pagination v-model:current-page="page" :page-size="10" :total="total" layout="total, prev, pager, next" :pager-count="5" @current-change="load" class="archive-pagination" />
  </el-dialog>
</template>
<script setup>
import { ref } from 'vue'
import { listRuns } from '@/api/runs'
import { shortDate } from '@/utils/presentation'
import { format, evaluationLabel } from '@/utils/telemetry'
defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'open-run'])
const loading = ref(false), error = ref(''), records = ref([]), page = ref(1), total = ref(0), flightId = ref('')
const statuses = { COMPLETED: '已完成', RUNNING: '未封存', INTERRUPTED: '已中断' }
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true; error.value = ''
  try {
    const response = await listRuns({ page: page.value, size: 10, flightId: flightId.value.trim() || undefined })
    if (id !== requestId) return
    records.value = response.data.records; total.value = response.data.total
  } catch { if (id === requestId) error.value = '无法读取档案，请确认持久化后台已经启动。' }
  finally { if (id === requestId) loading.value = false }
}
function open(id) { emit('open-run', id); emit('update:modelValue', false) }
</script>
<style scoped>
.archive-search{display:flex;gap:10px;margin:20px 0}.archive-search .el-input{flex:1}.archive-list{display:grid;gap:12px;min-height:100px}.archive-card{padding:16px 18px;border:1px solid var(--line);border-radius:9px}.archive-title{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.archive-title time{margin-left:auto;font-size:.8125rem;color:var(--muted)}.archive-role{font-size:.8125rem;color:var(--muted);line-height:1.7;margin:10px 0}.archive-bottom{display:flex;justify-content:space-between;align-items:center;gap:14px}.archive-bottom p{font-size:.875rem;line-height:1.8}.archive-bottom span{color:var(--muted)}.archive-card details{margin-top:10px;font-size:.8125rem;color:var(--muted);overflow-wrap:anywhere}.archive-card details p{margin:5px 0}.archive-pagination{justify-content:flex-end;margin-top:20px;flex-wrap:wrap}@media(max-width:600px){.archive-search{flex-wrap:wrap}.archive-card{padding:14px}.archive-title time{margin-left:0;flex-basis:100%}.archive-bottom{flex-wrap:wrap}.archive-bottom .el-button{width:100%}}
</style>
