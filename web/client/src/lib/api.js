// Small fetch layer: adds the Clerk session token and reads Server-Sent Events from POST responses.
let tokenGetter = async () => null
export const setTokenGetter = (fn) => { tokenGetter = fn }

async function headers(extra = {}) {
  const t = await tokenGetter().catch(() => null)
  return { ...extra, ...(t ? { Authorization: `Bearer ${t}` } : {}) }
}

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data }
}

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: await headers(body ? { 'Content-Type': 'application/json' } : {}),
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data)
  return data
}

export async function apiBlob(path, { method = 'POST' } = {}) {
  const res = await fetch(path, { method, headers: await headers() })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(data.error || 'Request failed', res.status, data)
  }
  return res.blob()
}

// POST and read the event stream: onEvent(eventName, data)
export async function stream(path, { json, form }, onEvent) {
  const res = await fetch(path, {
    method: 'POST',
    headers: await headers(json ? { 'Content-Type': 'application/json' } : {}),
    body: json ? JSON.stringify(json) : form,
  })
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, i)
      buf = buf.slice(i + 2)
      let event = 'message'
      const lines = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) lines.push(line.slice(5).trimStart())
      }
      if (!lines.length) continue
      try { onEvent(event, JSON.parse(lines.join('\n'))) } catch { /* ignore a malformed event */ }
    }
  }
}
