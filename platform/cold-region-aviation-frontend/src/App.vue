<template>
  <div class="workspace">
    <Sidebar />
    <div class="workspace-main">
      <header class="topbar">
        <span class="workspace-label">AirSim 仿真实验</span>
        <div class="connection-status">
          <span :class="{ down: !system.backendOnline }"><i class="dot" /> 后台 {{ system.backendOnline ? '已连接' : '未连接' }}</span>
          <span :class="{ down: !system.aiStatus.online }"><i class="dot" /> 推理 {{ system.aiStatus.online ? '在线' : '离线' }}</span>
          <el-button @click="showGuide = true">使用指南</el-button>
        </div>
      </header>
      <main id="main-content" class="main-content"><router-view /></main>
      <QuickStartDialog v-model="showGuide" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import QuickStartDialog from './components/QuickStartDialog.vue'
import { useSystemStatusStore } from '@/stores/systemStatus'
import { useTelemetryStore } from '@/stores/telemetry'
const route = useRoute()
const system = useSystemStatusStore()
const telemetry = useTelemetryStore()
const showGuide = ref(false)
onMounted(() => { system.startPolling(); telemetry.connect() })
onUnmounted(() => { system.stopPolling(); telemetry.disconnect() })
</script>
<style scoped>
.workspace{min-height:100vh;display:flex}.workspace-main{margin-left:208px;flex:1;min-width:0}.topbar{min-height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:10px 28px;background:#fff;gap:16px}.workspace-label{font-size:.875rem;color:var(--muted)}.connection-status{display:flex;gap:18px;font-size:.875rem;color:var(--green);align-items:center;flex-wrap:wrap}.connection-status .dot{margin-right:4px}.connection-status .down{color:#9b4528}.main-content{max-width:1500px;margin:auto;padding:24px 28px 40px}@media(max-width:1000px){.workspace-main{margin-left:184px}.topbar{padding:10px 20px}.main-content{padding:22px 20px}.workspace-label{display:none}}@media(max-width:760px){.workspace{display:block}.workspace-main{margin:0}.topbar{padding:8px 16px}.main-content{padding:20px 16px}.connection-status{width:100%;gap:12px;justify-content:space-between;font-size:.8125rem}.connection-status .el-button{font-size:.875rem}}
</style>
