import { numeric } from './telemetry.js'

export function streamLabel({ followLive, streaming, count, status, connected }) {
  if (!followLive) return '历史记录 · 不跟随新回放'
  if (streaming) return '正在回放'
  if (count && status === 'COMPLETED') return '回放已完成'
  if (count && status === 'INTERRUPTED') return '回放已中断'
  if (count && !connected) return '连接中断 · 保留已收数据'
  return count ? '暂无新数据' : '等待回放'
}
export function comparisonSummary(methods) {
  if (methods.length !== 3 || methods.some(m => !m.count || numeric(m.mape) === null)
      || new Set(methods.map(m => m.count)).size !== 1) return '等待三个方法在相同片段上完成验证。'
  const lstm = methods[0].mape, baseline = Math.min(methods[1].mape, methods[2].mape)
  if (Math.abs(lstm - baseline) < 0.0005) return '本次记录中，LSTM与误差较小的简单方法接近。'
  if (baseline <= 0) return '本次记录中，简单方法误差更小。'
  const percent = Math.abs((baseline - lstm) / baseline * 100).toFixed(1)
  return `本次记录中，LSTM比误差较小的简单方法${lstm < baseline ? '降低' : '增加'}了${percent}%的相对误差。`
}
// Choose by recency and completeness, never by model score.
export function defaultResearchRun(runs) {
  return runs.find(r => r.status === 'COMPLETED' && r.metrics?.verified_count > 0
    && r.configuration?.max_samples == null
    && Number.isInteger(r.sampleCount) && r.sampleCount > 0 && r.sampleCount === r.expectedSamples
    && r.configuration?.evaluation_role !== 'engineering_fault_injection' && !r.configuration?.engineering_test) || runs[0] || null
}
export function shortDate(value) { return value ? String(value).replace('T', ' ').slice(5, 19) : '时间未记录' }
export function replayCommand(path, flight = 'F022') {
  const quote = value => "'" + String(value).replaceAll("'", "'\\''") + "'"
  return `./demo/replay.sh ${quote(path)} ${quote(flight)} 2`
}
