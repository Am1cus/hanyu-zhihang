<template>
  <aside class="sidebar">
    <router-link to="/dashboard" class="brand" aria-label="寒域智航首页">
      <span class="brand-mark"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 23 16 5l10 18M10 18h12M16 5v22M6 23l10-5 10 5" /></svg></span>
      <span><strong>寒域智航</strong><small>无人机能耗实验室</small></span>
    </router-link>
    <div class="nav-label">实验工作台</div>
    <nav aria-label="主导航">
      <router-link v-for="item in items" :key="item.path" :to="item.path" class="nav-item">
        <component :is="item.icon" /><span>{{ item.label }}</span><span v-if="item.path === '/warning' && system.unhandledCount" class="nav-count">{{ system.unhandledCount }}</span>
      </router-link>
    </nav>
    <div class="sidebar-bottom">
      <div class="lab-label">仿真研究原型</div>
      <p>当前不用于真实飞行决策</p>
      <div class="boundary">V3候选 · V1/V2保留</div>
    </div>
  </aside>
</template>
<script setup>
import { Monitor, DataAnalysis, Bell } from '@element-plus/icons-vue'
import { useSystemStatusStore } from '@/stores/systemStatus'
const system = useSystemStatusStore()
const items = [
  { path: '/dashboard', label: '预测看板', icon: Monitor },
  { path: '/experiments', label: '模型对比', icon: DataAnalysis },
  { path: '/warning', label: '预警记录', icon: Bell }
]
</script>
<style scoped>
.sidebar{position:fixed;width:208px;height:100vh;background:#fff;border-right:1px solid var(--line);padding:28px 16px;display:flex;flex-direction:column;z-index:10}.brand{display:flex;gap:10px;align-items:center;color:var(--ink);margin:0 5px 40px}.brand:hover{text-decoration:none}.brand-mark{width:36px;height:40px;flex-shrink:0;background:var(--green);border-radius:7px;display:grid;place-items:center}.brand-mark svg{width:27px;fill:none;stroke:#fff;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}.brand strong{font-size:1.125rem;letter-spacing:1px}.brand small{display:block;font-size:.75rem;margin-top:5px;color:var(--muted)}.nav-label{font-size:.75rem;color:var(--muted);margin:0 12px 14px}.nav-item{display:flex;align-items:center;gap:12px;min-height:48px;padding:12px;margin-bottom:6px;border-radius:8px;color:var(--muted);font-size:1rem}.nav-item svg{width:19px;height:19px;flex-shrink:0}.nav-item:hover{background:#f0f5f2;text-decoration:none}.nav-item.router-link-active{background:#e7f1eb;color:var(--green);font-weight:650;box-shadow:inset 3px 0 var(--green)}.nav-count{margin-left:auto;font-size:.75rem;background:#fff0db;color:#8b4b11;padding:1px 5px;border-radius:4px}.sidebar-bottom{margin-top:auto;padding:20px 10px 0;color:var(--muted)}.lab-label{font-size:.875rem;color:var(--green)}.sidebar-bottom p,.boundary{font-size:.75rem;line-height:1.75;margin-top:10px}.boundary{border-top:1px solid var(--line);padding-top:12px}@media(max-width:1000px){.sidebar{width:184px;padding:24px 12px}.brand{gap:8px}.brand strong{font-size:1rem}}@media(max-width:760px){.sidebar{position:static;width:auto;height:auto;padding:16px 16px 6px}.brand{margin:0 0 14px}.nav-label,.sidebar-bottom{display:none}nav{display:flex;gap:6px}.nav-item{padding:10px 8px;gap:6px;font-size:.875rem;flex:1;justify-content:center;min-width:0;margin:0}.nav-item svg{width:17px;height:17px}.nav-item>span{white-space:nowrap}.nav-item.router-link-active{box-shadow:inset 0 -3px var(--green)}.nav-count{margin-left:0}}
</style>
