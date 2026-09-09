<template>
  <div class="workspace">
    <Sidebar />
    <div class="workspace-main">
      <header class="topbar">
        <span class="workspace-label">研发工作台 <span>/ {{ route.meta.title }}</span></span>
        <div class="connection-status">
          <span :class="{ down: !system.backendOnline }"><i class="dot" /> 后台 {{ system.backendOnline ? '已连接' : '未连接' }}</span>
          <span :class="{ down: !system.aiStatus.online }"><i class="dot" /> 推理 {{ system.aiStatus.online ? '在线' : '离线' }}</span>
          <span class="edition">AIRSIM · 仿真环境</span>
        </div>
      </header>
      <main class="main-content"><router-view /></main>
    </div>
  </div>
</template>
<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import { useSystemStatusStore } from '@/stores/systemStatus'
import { useTelemetryStore } from '@/stores/telemetry'
const route = useRoute()
const system = useSystemStatusStore()
const telemetry = useTelemetryStore()
onMounted(() => { system.startPolling(); telemetry.connect() })
onUnmounted(() => { system.stopPolling(); telemetry.disconnect() })
</script>
<style scoped>
.workspace{min-height:100vh;display:flex}.workspace-main{margin-left:210px;flex:1;min-width:0}.topbar{height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 34px;background:#fafaf6}.workspace-label{font-size:12px;color:var(--muted)}.workspace-label span{margin-left:12px;color:var(--ink)}.connection-status{display:flex;gap:18px;font-size:11px;color:var(--green);align-items:center}.connection-status .dot{margin-right:4px}.connection-status .down{color:#a16b37}.edition{color:var(--muted);border-left:1px solid var(--line);padding-left:18px;letter-spacing:.6px}.main-content{max-width:1530px;margin:auto;padding:32px 34px 40px}
@media(min-width:1600px){.main-content{padding-top:40px}}
@media(max-width:1000px){.workspace-main{margin-left:170px}.topbar{padding:0 22px}.main-content{padding:25px 22px}.edition{display:none}}
@media(max-width:760px){.workspace{display:block}.workspace-main{margin:0}.topbar{height:47px;padding:0 17px}.main-content{padding:23px 15px}.workspace-label{display:none}.connection-status{width:100%;justify-content:space-between}.edition{display:block;border:0;padding:0}}
</style>
