<template>
  <aside class="sidebar">
    <router-link to="/dashboard" class="brand" aria-label="寒域智航首页">
      <span class="brand-mark"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 23 16 5l10 18M10 18h12M16 5v22M6 23l10-5 10 5" /></svg></span>
      <span><strong>寒域智航</strong><small>HANYU · FLIGHT LAB</small></span>
    </router-link>
    <div class="nav-label">工作空间</div>
    <nav aria-label="主导航">
      <router-link v-for="item in items" :key="item.path" :to="item.path" class="nav-item">
        <component :is="item.icon" /><span>{{ item.label }}</span><span v-if="item.path === '/warning' && system.unhandledCount" class="nav-count">{{ system.unhandledCount }}</span>
      </router-link>
    </nav>
    <div class="sidebar-bottom">
      <div class="lab-label"><i class="dot" /> 实验原型 · V3候选 / V2保留</div>
      <p>面向寒区无人机的<br>电池容量预测研究</p>
      <div class="boundary">当前仅接入仿真数据<br>尚未完成真机验证</div>
    </div>
  </aside>
</template>
<script setup>
import { Monitor, DataAnalysis, Bell } from '@element-plus/icons-vue'
import { useSystemStatusStore } from '@/stores/systemStatus'
const system = useSystemStatusStore()
const items = [
  { path: '/dashboard', label: '飞行监测', icon: Monitor },
  { path: '/experiments', label: '实验验证', icon: DataAnalysis },
  { path: '/warning', label: '预警记录', icon: Bell }
]
</script>
<style scoped>
.sidebar{position:fixed;width:210px;height:100vh;background:#ecefe6;border-right:1px solid #dce1d3;padding:29px 18px;display:flex;flex-direction:column;z-index:10}.brand{display:flex;gap:10px;align-items:center;color:var(--ink);margin:0 5px 46px}.brand-mark{width:34px;height:38px;background:#365d46;border-radius:6px;display:grid;place-items:center}.brand-mark svg{width:27px;fill:none;stroke:#f1f5ea;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}.brand strong{font-size:18px;letter-spacing:2px;font-weight:600}.brand small{display:block;font-size:8px;letter-spacing:1px;margin-top:6px;color:var(--muted)}.nav-label{font-size:10px;color:#90978a;margin:0 12px 12px;letter-spacing:2px}.nav-item{display:flex;align-items:center;gap:12px;padding:13px 14px;margin-bottom:5px;border-radius:7px;color:#626d5e;font-size:13px}.nav-item svg{width:17px;height:17px}.nav-item:hover{background:#e3e8db}.nav-item.router-link-active{background:#dae4d4;color:#2b5138;font-weight:600}.nav-count{margin-left:auto;font-size:10px;background:#fff8ee;color:#a15c32;padding:1px 5px;border-radius:4px}.sidebar-bottom{margin-top:auto;padding:20px 10px 0}.lab-label{font-size:11px;color:#476443}.lab-label i{margin-right:4px}.sidebar-bottom p{font-size:12px;color:#747e6c;line-height:1.9;margin-top:12px}.boundary{font-size:10px;color:#8b9281;border-top:1px solid #d9dfd1;padding-top:15px;margin-top:20px;line-height:1.8}
@media(max-width:1000px){.sidebar{width:170px;padding:25px 10px}.brand{gap:8px}.brand strong{font-size:16px}.brand small{font-size:7px}}
@media(max-width:760px){.sidebar{position:static;width:auto;height:auto;padding:15px 16px 0}.brand{margin:0 0 18px}.nav-label,.sidebar-bottom{display:none}nav{display:flex;gap:7px}.nav-item{padding:10px;gap:7px;font-size:12px;flex:1;justify-content:center}.brand small{font-size:8px}}
</style>
<style scoped>
@media(max-width:760px){.nav-item{padding:10px 7px;gap:5px;min-width:0}.nav-item>span{white-space:nowrap}.nav-item svg{width:14px;height:14px;flex-shrink:0}.nav-count{margin-left:0;padding:1px 4px}}
</style>
