<script setup>
defineProps({ audit: { type: Object, default: null } })
defineEmits(['open-source'])
const actions = { create: '创建任务', pause: '暂停', resume: '继续运行', cancel: '结束任务', replay_origin: '关联原任务' }
const sources = { operator: '操作者', evaluation: '软件预演', replay: '复演', server_shutdown: '服务正常关闭' }
const number = value => Number.isFinite(value) ? value.toFixed(1) : '—'
</script>

<template>
  <section class="panel execution-audit">
    <div class="section-heading"><h2>操作记录</h2><span class="small-label">与算法决策分开保存</span></div>
    <p v-if="audit?.status !== 'recorded'" class="helper">该版本未保存操作记录，无法从档案确认暂停、继续或复演来源。原始任务数据保留。</p>
    <template v-else>
      <div v-if="audit.origin?.status === 'replay'" class="audit-origin"><div><strong>本任务由原档复演创建</strong><p class="archive-id">来源 {{ audit.origin.source_run_id }}</p></div><button class="button secondary small" @click="$emit('open-source', audit.origin.source_run_id)">查看原任务</button></div>
      <p class="helper">以下记录操作动作与仿真时刻。暂停不会被记作完成，复演不会覆盖原任务。</p>
      <div v-for="record in audit.records" :key="record.seq" class="decision-row"><time>{{ number(record.t_s) }} s</time><div><strong>{{ actions[record.action] || record.action }}</strong><p>{{ sources[record.source] || record.source }}<span v-if="record.source_run_id"> · 来源任务 {{ record.source_run_id }}</span></p></div></div>
    </template>
  </section>
</template>
