<script setup>
import { computed } from 'vue'
import { reasonText } from '../text'
const props = defineProps({ budget: { type: Object, default: null }, compact: Boolean, stopped: Boolean, mode: { type: String, default: 'segment' } })
const number = (value) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'
const valid = computed(() => props.budget?.status !== 'unavailable')
const value = (key) => valid.value ? props.budget?.[key] : null
const label = computed(() => {
  if (props.stopped) return props.budget?.status === 'unavailable' ? '已停止，预算未复算' : '已停止，历史预算'
  if (props.budget?.explanation === 'event_applied_waiting_for_next_grid_node_decision') return '等待下一节点重算'
  const scope = props.mode === 'mission' ? '三点往返' : '下一点往返'
  return { sufficient: `${scope}预算满足`, insufficient: `${scope}预算不足`, unavailable: '信息不足，无法核算' }[props.budget?.status] || '等待计算'
})
const explanation = computed(() => props.stopped && props.budget?.explanation === 'event_applied_waiting_for_next_grid_node_decision'
  ? '本次运行已停止；最后一次变化后的预算未复算，旧预算继续隐藏。'
  : reasonText(props.budget?.explanation) || '选择情景并计算，查看巡检与返程预算。')
const parts = computed(() => [
  { label: props.mode === 'mission' ? '三点巡检' : '下一巡检点', value: value('mission_task_wh') ?? value('next_task_wh'), color: 'var(--budget-task)' },
  { label: '返程', value: value('return_wh'), color: 'var(--budget-return)' },
  { label: '储备', value: value('reserve_wh'), color: 'var(--budget-reserve)' },
])
const total = computed(() => parts.value.reduce((sum, item) => sum + (item.value || 0), 0))
</script>

<template>
  <section :class="['energy-budget', { compact }]">
    <div class="section-heading"><h2>{{ mode === 'mission' ? '全任务往返预算' : '当前段往返预算' }}</h2><span :class="['badge', budget?.status || 'neutral']">{{ label }}</span></div>
    <div class="budget-main"><div><span>当前可用</span><strong>{{ number(budget?.available_wh) }} <small>Wh</small></strong></div><div><span>{{ mode === 'mission' ? '完整往返所需（含储备）' : '下一段往返所需（含储备）' }}</span><strong>{{ number(value('required_wh')) }} <small>Wh</small></strong></div></div>
    <div v-if="budget && total > 0" class="budget-bar" aria-label="任务预算构成"><i v-for="part in parts" :key="part.label" :style="{ width: `${(part.value || 0) / total * 100}%`, background: part.color }"></i></div>
    <div class="budget-parts"><span v-for="(part, index) in parts" :key="part.label"><span class="ledger-label"><i :style="{ background: part.color }"></i><span class="ledger-number">0{{ index + 1 }}</span>{{ part.label }}</span><b>{{ number(part.value) }} <small>Wh</small></b></span></div>
    <p class="budget-margin">预算余量 <b :class="{ negative: value('margin_wh') < 0 }">{{ number(value('margin_wh')) }} Wh</b></p>
    <p v-if="mode === 'mission'" class="budget-prefix">当前预算可支持 <b>{{ value('feasible_prefix_count') ?? '—' }} / {{ budget?.target_count ?? 3 }} 点</b></p>
    <p v-if="mode === 'mission'" class="helper">整任务预算使用声明的上界功率。执行中逐段重算，最终完成量见策略结果；不预知未来事件。</p>
    <p class="helper">{{ explanation }}</p>
  </section>
</template>
