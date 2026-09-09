<template>
  <div class="drone-management fade-in">
    <div class="page-header">
      <h1 class="page-title">无人机管理</h1>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon> 添加无人机
      </el-button>
    </div>

    <!-- 搜索栏 -->
    <el-card style="margin-bottom: 16px;">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="编号/名称/型号" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable>
            <el-option label="离线" :value="0" />
            <el-option label="在线" :value="1" />
            <el-option label="飞行中" :value="2" />
            <el-option label="告警" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchDrones">查询</el-button>
          <el-button @click="resetSearch">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <el-card>
      <el-table :data="droneList" stripe v-loading="loading">
        <el-table-column prop="droneCode" label="编号" width="120" />
        <el-table-column prop="droneName" label="名称" width="140" />
        <el-table-column prop="model" label="型号" width="180" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" effect="dark" size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="batteryLevel" label="电量(%)" width="100" />
        <el-table-column prop="maxRange" label="最大航程(km)" width="130" />
        <el-table-column prop="maxSpeed" label="最大速度(m/s)" width="130" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="editDrone(row)">编辑</el-button>
            <el-button size="small" type="info" link @click="viewDetail(row)">详情</el-button>
            <el-popconfirm title="确认删除该无人机？" @confirm="removeDrone(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page.current"
        v-model:page-size="page.size"
        :total="page.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 16px; justify-content: flex-end;"
        @size-change="fetchDrones"
        @current-change="fetchDrones"
      />
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showDialog" :title="editingDrone ? '编辑无人机' : '添加无人机'" width="560px" destroy-on-close>
      <el-form :model="droneForm" label-width="100px">
        <el-form-item label="编号" required>
          <el-input v-model="droneForm.droneCode" placeholder="如：UAV-001" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="droneForm.droneName" placeholder="如：寒域一号" />
        </el-form-item>
        <el-form-item label="型号">
          <el-input v-model="droneForm.model" placeholder="如：DJI Matrice 300 RTK" />
        </el-form-item>
        <el-form-item label="制造商">
          <el-input v-model="droneForm.manufacturer" />
        </el-form-item>
        <el-form-item label="最大载荷(kg)">
          <el-input-number v-model="droneForm.maxPayload" :min="0" :precision="1" />
        </el-form-item>
        <el-form-item label="最大航程(km)">
          <el-input-number v-model="droneForm.maxRange" :min="0" :precision="1" />
        </el-form-item>
        <el-form-item label="最大速度(m/s)">
          <el-input-number v-model="droneForm.maxSpeed" :min="0" :precision="1" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="droneForm.remark" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDrone">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { addDrone, deleteDrone, getDroneList, updateDrone } from '@/api/drone'

const loading = ref(false)
const showDialog = ref(false)
const editingDrone = ref(null)
const droneList = ref([])
const searchForm = ref({ keyword: '', status: null })
const page = ref({ current: 1, size: 10, total: 0 })
const droneForm = ref({})

onMounted(() => { fetchDrones() })

const fetchDrones = async () => {
  loading.value = true
  try {
    const response = await getDroneList({
      pageNum: page.value.current,
      pageSize: page.value.size,
      keyword: searchForm.value.keyword || undefined,
      status: searchForm.value.status
    })
    droneList.value = response.data?.records || []
    page.value.total = Number(response.data?.total || 0)
  } finally {
    loading.value = false
  }
}

const resetSearch = () => { searchForm.value = { keyword: '', status: null }; fetchDrones() }
const openCreateDialog = () => { editingDrone.value = null; droneForm.value = {}; showDialog.value = true }
const editDrone = (row) => { editingDrone.value = row; droneForm.value = { ...row }; showDialog.value = true }
const viewDetail = (row) => { ElMessage.info(`查看无人机：${row.droneName}`) }
const removeDrone = async (id) => {
  await deleteDrone(id)
  ElMessage.success('删除成功')
  await fetchDrones()
}
const submitDrone = async () => {
  if (!droneForm.value.droneCode || !droneForm.value.droneName) {
    ElMessage.warning('请填写无人机编号和名称')
    return
  }
  if (editingDrone.value) await updateDrone(droneForm.value)
  else await addDrone({ status: 1, ...droneForm.value })
  showDialog.value = false
  editingDrone.value = null
  droneForm.value = {}
  ElMessage.success('保存成功')
  await fetchDrones()
}
const getStatusType = (s) => ({ 0: 'info', 1: 'success', 2: 'primary', 3: 'warning', 4: 'danger' }[s] || 'info')
const getStatusText = (s) => ({ 0: '离线', 1: '在线', 2: '飞行中', 3: '告警', 4: '紧急' }[s] || '未知')
</script>
