const ROOT = '/api/competition'

export async function request(path, options = {}) {
  const response = await fetch(`${ROOT}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'string' ? body : body.detail || body.message || `请求失败 (${response.status})`
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    error.status = response.status
    throw error
  }
  return body
}

export const api = {
  scenarios: () => request('/scenarios'),
  evaluate: (body) => request('/evaluate', { method: 'POST', body: JSON.stringify(body) }),
  createRun: (body) => request('/runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => request('/runs'),
  run: (id, signal) => request(`/runs/${encodeURIComponent(id)}`, { signal }),
  event: (id, body) => request(`/runs/${encodeURIComponent(id)}/events`, { method: 'POST', body: JSON.stringify(body) }),
  control: (id, action) => request(`/runs/${encodeURIComponent(id)}/control`, { method: 'POST', body: JSON.stringify({ action }) }),
  exportUrl: (id) => `${ROOT}/runs/${encodeURIComponent(id)}/export`,
}
