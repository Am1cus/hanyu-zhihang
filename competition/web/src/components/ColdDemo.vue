<script setup>
import { computed } from 'vue'
import { reasonText } from '../text'
const props = defineProps({ comparison: { type: Object, required: true }, disabled: Boolean })
defineEmits(['start', 'close'])
const cases = computed(() => [
  { temperature: 0, evaluation: props.comparison.mild },
  { temperature: -20, evaluation: props.comparison.cold },
].map(item => {
  const run = item.evaluation.runs.find(run => run.strategy === 'energy')
  const budget = item.evaluation.whole_mission_budget.energy
  return { ...item, run, budget, available: run.status === 'COMPLETED' && budget.status !== 'unavailable' }
}))
const canStart = computed(() => cases.value.every(item => item.available) && cases.value[1].run.summary.returned)
const number = value => Number.isFinite(value) ? value.toFixed(2) : '—'
</script>

<template>
  <section class="panel cold-demo" aria-labelledby="cold-demo-title">
    <div class="section-heading"><div><span class="eyebrow">看懂一次任务取舍</span><h2 id="cold-demo-title">同样三个点，低温后能完成几个？</h2></div><button class="button secondary small" @click="$emit('close')">收起案例</button></div>
    <p class="helper">同一地图、55% 初始 SOC（容量比例）、20% 参考储备与能量策略，只改变温度。以下是后端完整软件预演结果。</p>
    <div class="cold-demo-cases">
      <article v-for="item in cases" :key="item.temperature" :class="['cold-demo-case', { 'cold-case': item.temperature < 0 }]">
        <div class="section-heading"><h3>{{ item.temperature }} °C</h3><span :class="['badge', item.run.summary.returned ? 'completed' : 'failed']">{{ !item.available ? '预演不可用' : item.run.summary.returned ? '已返回基地' : '未返回基地' }}</span></div>
        <p v-if="item.available" class="demo-outcome">预演完成 <strong>{{ item.run.summary.visited_count }}<small> / {{ item.run.targets.length }} 点</small></strong></p>
        <p v-else class="negative">{{ item.run.status === 'UNAVAILABLE' ? '信息不足，预演未执行。' : '预演未完成。' }} {{ reasonText(item.run.summary.ended_reason || item.budget.explanation) }}</p>
        <dl class="demo-budget-facts"><div><dt>起飞可用能量</dt><dd>{{ number(item.budget.available_wh) }} Wh</dd></div><div><dt>完整往返预算</dt><dd>{{ number(item.budget.required_wh) }} Wh</dd></div><div><dt>起飞时保守预算支持</dt><dd>{{ item.budget.feasible_prefix_count ?? '—' }} 点</dd></div></dl>
      </article>
    </div>
    <div class="demo-takeaway"><strong>每接下一项巡检，先算回程和储备。</strong><p>起飞预算采用上界功率，运行中逐点重算，最终完成量可能不同。任务量减少时，耗能下降不能作为节能比较。</p></div>
    <div class="demo-actions"><button class="button primary" :disabled="disabled || !canStart" @click="$emit('start')">{{ canStart ? '运行 −20 °C 案例，观察一点后返程' : '参考参数不可用，暂不能运行此案例' }}</button><span class="helper">{{ canStart ? '20 倍仿真，约 26 秒播放 · 没有真实飞机' : '先检查参考参数或预演结束原因，再运行任务。' }}</span></div>
  </section>
</template>
