<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="历史实验记录" width="min(1080px, 94vw)" @open="load">
    <p class="footnote">每次回放单独存档；重复回放不增加独立架次数。误差由后台存档计算，故障注入记录不作精度证据。</p>
    <form class="archive-search" @submit.prevent="page = 1; load()"><el-input v-model="flightId" placeholder="按完整架次ID筛选，如 flight_036" clearable aria-label="架次筛选" /><el-button type="primary" native-type="submit" :loading="loading">查询记录</el-button></form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="records" v-loading="loading" empty-text="暂无已保存实验，请运行一次回放">
      <el-table-column label="架次 / 运行编号" min-width="220"><template #default="{ row }"><strong>{{ row.flightId }}</strong><div class="mono short-id">{{ row.runId.slice(0, 8) }}</div><div class="short-id">{{ evaluationLabel(row.configuration?.evaluation_role || 'legacy_V2') }}</div><div v-if="row.configuration?.engineering_test" class="short-id">工程回放检查 · 非新数据</div></template></el-table-column>
      <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ row.createdAt?.replace('T', ' ').slice(0,19) }}</template></el-table-column>
      <el-table-column label="样本" width="85"><template #default="{ row }">{{ row.sampleCount }}/{{ row.expectedSamples }}</template></el-table-column>
      <el-table-column label="状态" width="95"><template #default="{ row }"><span class="pill" :class="{ idle: row.status !== 'COMPLETED' }">{{ statuses[row.status] || row.status }}</span></template></el-table-column>
      <el-table-column label="已验证 / 有效预测" min-width="145"><template #default="{ row }">{{ row.metrics.verified_count || 0 }} / {{ row.metrics.valid_count || 0 }}</template></el-table-column>
      <el-table-column label="耗电量 MAPE" min-width="125"><template #default="{ row }">{{ format(row.metrics.mape_pct, 3) }} %</template></el-table-column>
      <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button type="primary" link @click="open(row.runId)">打开记录</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="10" :total="total" layout="total, prev, pager, next" @current-change="load" class="archive-pagination" />
  </el-dialog>
</template>
<script setup>
import { ref } from 'vue'
import { listRuns } from '@/api/runs'
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
.archive-search{display:flex;gap:10px;margin:20px 0}.archive-search .el-input{max-width:350px}.short-id{font-size:10px;color:var(--muted);margin-top:4px}.archive-pagination{justify-content:flex-end;margin-top:20px}@media(max-width:600px){.archive-search{flex-wrap:wrap}}
</style>
