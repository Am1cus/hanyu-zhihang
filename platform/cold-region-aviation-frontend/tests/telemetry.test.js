import test from 'node:test'
import assert from 'node:assert/strict'
import { numeric, format, orderedRows, verifiedPairs, pairMetrics, comparisonMetrics, evaluationLabel } from '../src/utils/telemetry.js'
const at = seconds => new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString()
const row = (seconds, capacity, prediction = null) => ({ collectTime: at(seconds), remainingCapacityAh: capacity, prediction })
const prediction = { valid: true, forecast_horizon_s: 10, predicted_consumption_Ah: 0.05 }

test('missing values are unavailable, never zero', () => {
  for (const value of [null, undefined, '', 'bad', Infinity]) { assert.equal(numeric(value), null); assert.equal(format(value), '—') }
  assert.equal(numeric(0), 0)
})
test('sorts and deduplicates by measurement timestamp', () => {
  const rows = orderedRows([row(10, 1), row(0, 1.1), row(10, .9)])
  assert.equal(rows.length, 2)
  assert.equal(rows[1].remainingCapacityAh, .9)
})
test('a forecast verifies only against its actual target time', () => {
  const pairs = verifiedPairs([row(0, 1, prediction), row(2, .99), row(10, .949)])
  assert.equal(pairs.length, 1)
  assert.ok(Math.abs(pairs[0].actual - 51) < 1e-9)
  assert.equal(pairs[0].predicted, 50)
})
test('a missing target is not filled with the next sample', () => {
  assert.equal(verifiedPairs([row(0, 1, prediction), ...Array.from({length:10}, (_, i) => row(i + 11, .9))]).length, 0)
})
test('missing capacities and invalid forecasts do not count', () => {
  assert.equal(verifiedPairs([row(0, 1, {...prediction, valid:false}), row(10, .9)]).length, 0)
  assert.equal(verifiedPairs([row(0, 1, prediction), row(10, null)]).length, 0)
})
test('zero actual consumption is excluded only from MAPE, not MAE', () => {
  assert.deepEqual(pairMetrics([]), {count:0, mae:null, mape:null})
  assert.deepEqual(pairMetrics([{actual:0, predicted:1}]), {count:1, mae:1, mape:null})
})

test('identical source timestamps in different runs never cross-match', () => {
  const a = { ...row(0, 1, prediction), runId: 'a', sourceTimeS: 0 }
  const b = { ...row(10, .95), runId: 'b', sourceTimeS: 10 }
  assert.equal(verifiedPairs([a, b]).length, 0)
  assert.equal(orderedRows([a, { ...a, runId: 'b' }]).length, 2)
  assert.equal(verifiedPairs([a, { ...b, runId: 'a' }]).length, 1)
})

test('capacity increases cannot become valid discharge labels', () => {
  assert.equal(verifiedPairs([row(0, 1, prediction), row(10, 1.1)]).length, 0)
})

function v3Rows() {
  return Array.from({length:11},(_,i)=>({
    ...row(i,1-i*.005,i===0?{...prediction,execution_mode:'research_shadow',baselines:{history_10s:.06,mean_current_20s:.04}}:null),
    runId:'v3',sampleSeq:i,sourceTimeS:i,velocityX:1,velocityY:0,velocityZ:0,windX:0,windY:0,windZ:0,
    current:18,windSpeed:0,voltage:11,batteryLevel:50,envTemperature:-20,speed:1,altitude:10
  }))
}
test('V3 methods use identical labels and preserve original outputs',()=>{
  const rows=v3Rows(), saved=JSON.stringify(rows), methods=comparisonMetrics(rows)
  assert.deepEqual(methods.map(m=>m.count),[1,1,1])
  assert.ok(methods[0].mape<1e-9)
  assert.ok(Math.abs(methods[1].mape-20)<1e-9)
  assert.ok(Math.abs(methods[2].mape-20)<1e-9)
  assert.equal(JSON.stringify(rows),saved)
})
test('V3 labels cannot span gaps or incomplete future observations',()=>{
  const missing=v3Rows();missing.splice(5,1)
  assert.equal(verifiedPairs(missing).length,0)
  const incomplete=v3Rows();incomplete[5].windX=null
  assert.equal(verifiedPairs(incomplete).length,0)
  const archived=v3Rows();archived[0].verification={status:'invalid_target'}
  assert.equal(verifiedPairs(archived).length,0)
  for (const [field,value] of [['windX',201],['voltage',0],['batteryLevel',101],['envTemperature',-61]]) {
    const outside=v3Rows();outside[5][field]=value
    assert.equal(verifiedPairs(outside).length,0,field)
  }
})
test('missing baselines do not become zero-valued competing methods',()=>{
  const rows=v3Rows();delete rows[0].prediction.baselines.mean_current_20s
  assert.deepEqual(comparisonMetrics(rows).map(m=>m.count),[0,0,0])
})
test('training and post-selection test roles are explicitly labelled',()=>{
  assert.match(evaluationLabel('training'),/不作泛化/)
  assert.match(evaluationLabel('exploratory_test'),/选型分析/)
})
