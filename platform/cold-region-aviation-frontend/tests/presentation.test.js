import test from 'node:test'
import assert from 'node:assert/strict'
import { streamLabel, comparisonSummary, defaultResearchRun, shortDate, replayCommand } from '../src/utils/presentation.js'

test('history view never claims to be live when new data arrives',()=>{
  assert.match(streamLabel({followLive:false,streaming:true,count:50,status:'RUNNING',connected:true}),/历史记录/)
})
test('completed and disconnected states are distinct from waiting for replay',()=>{
  assert.equal(streamLabel({followLive:true,count:195,status:'COMPLETED',connected:true}),'回放已完成')
  assert.match(streamLabel({followLive:true,count:20,status:'RUNNING',connected:false}),/连接中断/)
  assert.equal(streamLabel({followLive:true,count:0,connected:true}),'等待回放')
})
test('best and worst comparisons use the strongest simple baseline',()=>{
  const rows=[{count:100,mape:2},{count:100,mape:8},{count:100,mape:4}]
  assert.match(comparisonSummary(rows),/降低了50.0%/)
  rows[0].mape=6
  assert.match(comparisonSummary(rows),/增加了50.0%/)
})
test('missing or mismatched comparison samples do not generate a performance claim',()=>{
  assert.match(comparisonSummary([{count:0,mape:null},{count:0,mape:null},{count:0,mape:null}]),/等待/)
  assert.match(comparisonSummary([{count:1,mape:1},{count:2,mape:2},{count:1,mape:3}]),/等待/)
  assert.match(comparisonSummary([{count:1,mape:1},{count:1,mape:null},{count:1,mape:3}]),/等待/)
})
test('equal and zero-baseline errors have finite honest descriptions',()=>{
  assert.match(comparisonSummary([{count:1,mape:2},{count:1,mape:2},{count:1,mape:3}]),/接近/)
  assert.match(comparisonSummary([{count:1,mape:1},{count:1,mape:0},{count:1,mape:3}]),/简单方法误差更小/)
})
test('default selection is based on recency not cherry-picked accuracy',()=>{
  const fault={runId:'fault',status:'COMPLETED',metrics:{verified_count:1,mape_pct:0},configuration:{evaluation_role:'engineering_fault_injection'}}
  const partial={runId:'partial',status:'COMPLETED',metrics:{verified_count:1},configuration:{engineering_test:'browser'}}
  const ordinary={runId:'latest',status:'COMPLETED',sampleCount:195,expectedSamples:195,metrics:{verified_count:156,mape_pct:9},configuration:{}}
  const best={...ordinary,runId:'best',metrics:{verified_count:156,mape_pct:1}}
  const truncated={...ordinary,runId:'truncated',configuration:{max_samples:195}}
  const incomplete={...ordinary,runId:'incomplete',sampleCount:150}
  assert.equal(defaultResearchRun([fault,partial,truncated,incomplete,ordinary,best]).runId,'latest')
  assert.equal(defaultResearchRun([]),null)
})
test('replay command quotes spaces, command substitutions and literal quotes',()=>{
  assert.equal(replayCommand('/a b/data.zip'),"./demo/replay.sh '/a b/data.zip' 'F022' 2")
  assert.ok(replayCommand("a'$(whoami)").includes("'a'\\''$(whoami)'"))
})
test('record time retains seconds so repeat runs can be distinguished',()=>{
  assert.equal(shortDate('2026-09-10T12:34:56'),'09-10 12:34:56')
  assert.equal(shortDate(null),'时间未记录')
})
