export function numeric(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}
export function format(value, digits = 2) {
  const number = numeric(value)
  return number === null ? '—' : number.toFixed(digits)
}
export function timestamp(value) {
  if (!value) return null
  const result = new Date(String(value).replace(' ', 'T')).getTime()
  return Number.isFinite(result) ? result : null
}
export function orderedRows(rows) {
  const unique = new Map()
  for (const row of rows) {
    const sourceTime = numeric(row.sourceTimeS)
    const time = sourceTime === null ? timestamp(row.collectTime) : sourceTime * 1000
    if (time !== null) unique.set((row.runId || 'legacy') + ':' + time, { ...row, time })
  }
  return [...unique.values()].sort((a, b) => a.time - b.time)
}
// Match the server's V3 label-quality gates while future values are still live.
function validV3Observation(row) {
  const ranges = { envTemperature: [-60, 60], windSpeed: [0, 100], voltage: [0, 100, true],
    current: [-1000, 1000], batteryLevel: [0, 100], speed: [0, 200], altitude: [-1000, 20000],
    remainingCapacityAh: [0, 1000, true], velocityX: [-200, 200], velocityY: [-200, 200],
    velocityZ: [-200, 200], windX: [-200, 200], windY: [-200, 200], windZ: [-200, 200] }
  return Object.entries(ranges).every(([key, [min, max, strict]]) => {
    const value = numeric(row?.[key])
    return value !== null && (strict ? value > min : value >= min) && value <= max
  })
}
// Match by target timestamp, never by array index: gaps must not become false labels.
export function verifiedPairs(rows) {
  const ordered = orderedRows(rows)
  const byTime = new Map(ordered.map(row => [(row.runId || 'legacy') + ':' + row.time, row]))
  return ordered.flatMap(row => {
    const prediction = row.prediction
    const horizon = numeric(prediction?.forecast_horizon_s)
    const predicted = numeric(prediction?.predicted_consumption_Ah)
    const current = numeric(row.remainingCapacityAh)
    if (!prediction?.valid || horizon === null || horizon <= 0 || predicted === null || current === null) return []
    if (row.verification?.status === 'invalid_target') return []
    const target = byTime.get((row.runId || 'legacy') + ':' + (row.time + horizon * 1000))
    const actual = numeric(target?.remainingCapacityAh)
    if (actual === null || actual < 0 || actual > current) return []
    if (prediction.execution_mode === 'research_shadow') {
      // No labels spanning missing or invalid future observations, including live feeds.
      for (let second = 1; second <= horizon; second++) {
        const observed = byTime.get((row.runId || 'legacy') + ':' + (row.time + second * 1000))
        const previous = byTime.get((row.runId || 'legacy') + ':' + (row.time + (second - 1) * 1000))
        const q = numeric(observed?.remainingCapacityAh), lastQ = numeric(previous?.remainingCapacityAh)
        if (!observed || q === null || lastQ === null || q < 0 || q > lastQ + 1e-9) return []
        if (observed.sampleSeq !== previous.sampleSeq + 1) return []
        if (!validV3Observation(observed) || !validV3Observation(previous)) return []
      }
    }
    const history = numeric(prediction.baselines?.history_10s), mean = numeric(prediction.baselines?.mean_current_20s)
    return [{ time: row.time, targetTime: target.time, predicted: predicted * 1000, actual: (current - actual) * 1000,
      history: history === null ? null : history * 1000, mean: mean === null ? null : mean * 1000 }]
  })
}
export function comparisonMetrics(rows) {
  const pairs = verifiedPairs(rows).filter(p => p.history !== null && p.mean !== null && p.actual > 1e-6)
  return [['predicted','LSTM V3候选'],['history','延续过去10秒耗电'],['mean','过去20秒均流估算']].map(([key,name]) => ({
    key, name, ...pairMetrics(pairs.map(p => ({ actual: p.actual, predicted: p[key] })))
  }))
}
export function evaluationLabel(role) {
  return ({ training: '训练架次 · 不作泛化证据', development_validation: '开发验证架次',
    exploratory_test: '探索性测试 · 已参与选型分析', exploratory_extra: '探索性补充 · 已参与选型分析',
    unconfirmed_new_data: '新数据 · 尚未完成独立确认', engineering_fault_injection: '工程故障注入 · 不作模型精度证据', legacy_V2: '旧版 V2 实验' })[role] || role || '身份未提供'
}
export function pairMetrics(pairs) {
  if (!pairs.length) return { count: 0, mae: null, mape: null }
  const percentages = pairs.filter(p => Math.abs(p.actual) > 1e-6)
  return {
    count: pairs.length,
    mae: pairs.reduce((sum, p) => sum + Math.abs(p.actual - p.predicted), 0) / pairs.length,
    mape: percentages.length ? percentages.reduce((sum, p) => sum + Math.abs((p.actual - p.predicted) / p.actual) * 100, 0) / percentages.length : null
  }
}
export function downloadJson(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
