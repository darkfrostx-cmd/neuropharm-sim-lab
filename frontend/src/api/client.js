const DEFAULT_TIMEOUT = 15000

function resolveBaseUrl() {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (!raw) {
    return ''
  }
  return raw.endsWith('/') ? raw.slice(0, -1) : raw
}

const API_BASE_URL = resolveBaseUrl()

async function withTimeout(promise, timeoutMs = DEFAULT_TIMEOUT) {
  if (!timeoutMs) {
    return promise
  }
  let timer
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error('Request timed out'))
    }, timeoutMs)
  })
  try {
    const result = await Promise.race([promise, timeoutPromise])
    return result
  } finally {
    clearTimeout(timer)
  }
}

async function apiRequest(path, { method = 'POST', payload, headers = {}, timeout } = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`
  const response = await withTimeout(
    fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: method === 'GET' ? undefined : JSON.stringify(payload ?? {}),
      credentials: 'include',
    }),
    timeout,
  )

  const contentType = response.headers.get('content-type')
  const isJson = contentType && contentType.includes('application/json')
  const body = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const message = isJson && body?.message ? body.message : response.statusText || 'Request failed'
    const context = isJson && body?.context ? body.context : undefined
    const error = new Error(message || 'Request failed')
    error.status = response.status
    error.code = body?.code
    if (context) {
      error.context = context
    }
    throw error
  }

  return body
}

export function post(path, payload, options = {}) {
  return apiRequest(path, { ...options, method: 'POST', payload })
}

export function get(path, options = {}) {
  return apiRequest(path, { ...options, method: 'GET' })
}

export function apiBaseUrl() {
  return API_BASE_URL
}

