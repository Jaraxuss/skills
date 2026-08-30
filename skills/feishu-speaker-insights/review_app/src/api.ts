let csrfToken = ''

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken
  const response = await fetch('/api/v1/csrf', { credentials: 'same-origin' })
  if (!response.ok) throw new Error('无法初始化本地审核会话')
  const payload = await response.json()
  csrfToken = payload.token
  return csrfToken
}

export async function api(path: string, init: RequestInit = {}) {
  const modifying = ['POST', 'PUT', 'PATCH', 'DELETE'].includes((init.method || 'GET').toUpperCase())
  const headers = new Headers(init.headers)
  if (modifying) {
    headers.set('X-CSRF-Token', await ensureCsrf())
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败（${response.status}）`)
  }
  return response.json()
}

export const getCustomers = () => api('/api/v1/customers')
export const getSummary = () => api('/api/v1/console/summary')
export const getFiles = (customerId: string) => api(`/api/v1/customers/${encodeURIComponent(customerId)}/files`)
export const getTranscriptPreview = (customerId: string, path: string) => api(`/api/v1/customers/${encodeURIComponent(customerId)}/transcript-preview?path=${encodeURIComponent(path)}`)
export const getTranscriptSpeakers = (customerId: string, paths: string[]) => api(`/api/v1/customers/${encodeURIComponent(customerId)}/transcript-speakers`, { method: 'POST', body: JSON.stringify({ paths }) })
export const getSessions = () => api('/api/v1/enrollment-sessions')
export const getSession = (id: string) => api(`/api/v1/enrollment-sessions/${encodeURIComponent(id)}`)
export const getProfiles = (id: string) => api(`/api/v1/customers/${encodeURIComponent(id)}/profiles`)
export const getCandidates = (id: string) => api(`/api/v1/customers/${encodeURIComponent(id)}/candidates`)
