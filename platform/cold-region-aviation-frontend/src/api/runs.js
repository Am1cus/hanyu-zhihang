import request from './request'

export const listRuns = params => request.get('/runs', { params, silent: true })
export const getRun = id => request.get('/runs/' + encodeURIComponent(id), { silent: true })
export const getRunEvents = (id, afterSeq = -1, limit = 1000) => request.get('/runs/' + encodeURIComponent(id) + '/events', { params: { afterSeq, limit }, silent: true })
export const recheckRun = (id, sampleSeq) => request.post('/runs/' + encodeURIComponent(id) + '/recheck', null, { params: { sampleSeq }, silent: true })
export const getRechecks = id => request.get('/runs/' + encodeURIComponent(id) + '/rechecks', { silent: true })

export async function exportRun(id) {
  const [run, checks] = await Promise.all([getRun(id), getRechecks(id)])
  const events = []
  let afterSeq = -1
  while (true) {
    const response = await getRunEvents(id, afterSeq)
    const chunk = response.data || []
    events.push(...chunk)
    if (!chunk.length || chunk.length < 1000) break
    afterSeq = chunk.at(-1).telemetry.sampleSeq
  }
  return { schema_version: 1, run: run.data, events, rechecks: checks.data, exported_at: new Date().toISOString() }
}
