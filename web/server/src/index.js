// Kasafi web app server.
// - Clerk authentication (social login) on every /api route
// - profiles (name + organisation) and chat history in SQLite
// - forwards questions to the Kasafi engine (N-ATLaS + Hausa-ASR, running on the GPU machine) and streams its
//   progress back to the browser as Server-Sent Events
import express from 'express'
import multer from 'multer'
import rateLimit from 'express-rate-limit'
import fs from 'node:fs'
import path from 'node:path'
import { clerkMiddleware, clerkClient, getAuth } from '@clerk/express'
import { profiles, sessions, messages } from './db.js'

const { PORT = 3001, ENGINE_URL = '', ENGINE_API_KEY = '', CLIENT_DIST = '../client/dist', ADMIN_EMAILS = '' } = process.env
const ADMINS = new Set(ADMIN_EMAILS.split(',').map((e) => e.trim().toLowerCase()).filter(Boolean))
const AUDIO_DIR = path.resolve(path.dirname(process.env.DB_PATH || './data/x'), 'audio')
fs.mkdirSync(AUDIO_DIR, { recursive: true })

const app = express()
app.set('trust proxy', 1)               // behind nginx
app.disable('x-powered-by')
app.use(express.json({ limit: '64kb' }))
app.use(clerkMiddleware())
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 8 * 1024 * 1024 } })

// ---------------------------------------------------------------- helpers
const requireUser = (req, res, next) => {
  const { userId } = getAuth(req)
  if (!userId) return res.status(401).json({ error: 'Sign in to continue.' })
  req.userId = userId
  next()
}
const requireProfile = (req, res, next) => {
  req.profile = profiles.get(req.userId)
  if (!req.profile) return res.status(428).json({ error: 'profile_required' })
  next()
}
const askLimit = rateLimit({ windowMs: 60_000, limit: 20, keyGenerator: (req) => req.userId,
  message: { error: 'Too many questions in a minute. Wait a moment and ask again.' } })

const engine = (p, init = {}) => {
  if (!ENGINE_URL) throw new Error('ENGINE_URL is not set')
  return fetch(ENGINE_URL.replace(/\/$/, '') + p, { ...init, headers: { ...(init.headers || {}), 'x-api-key': ENGINE_API_KEY } })
}
const titleFrom = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 60) || 'Sabuwar tattaunawa'

function parseEvent(raw) {
  let event = 'message'; const data = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!data.length) return null
  try { return { event, data: JSON.parse(data.join('\n')) } } catch { return null }
}

const send = (res, event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)

// Relay the engine's event stream to the browser; save the answer when it arrives (even if the browser left).
async function relay(res, engineRes, { session, userMsg }) {
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive', 'X-Accel-Buffering': 'no' })
  const { id, title, created_at, updated_at } = session
  send(res, 'meta', { session: { id, title, created_at, updated_at }, userMessage: userMsg })
  if (!engineRes.ok) {
    const msg = engineRes.status === 503 ? 'Kasafi engine is starting or offline. Try again in a minute.'
      : 'The engine could not answer. Try again.'
    send(res, 'error', { message: msg }); return res.end()
  }
  const reader = engineRes.body.getReader(); const dec = new TextDecoder(); let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2)
      const ev = parseEvent(raw)
      if (!ev) { if (!res.writableEnded) res.write(raw + '\n\n'); continue }
      if (ev.event === 'stage' && ev.data.stage === 'heard' && userMsg) {
        messages.update(userMsg.id, { content: ev.data.text, transcript: ev.data.text })
        if (session.title === 'Sakon murya') { sessions.rename(session.userId, session.id, titleFrom(ev.data.text)); session.title = titleFrom(ev.data.text) }
      }
      if (ev.event === 'answer') {
        const saved = messages.add(session.id, { role: 'assistant', content: ev.data.text, interaction_id: ev.data.interaction_id,
          lang: ev.data.lang, voice: ev.data.voice, transcript: ev.data.transcript })
        if (!res.writableEnded) send(res, 'answer', { ...ev.data, message: saved, session: { id: session.id, title: session.title } })
        continue
      }
      if (!res.writableEnded) res.write(raw + '\n\n')
    }
  }
  if (!res.writableEnded) res.end()
}

function sessionFor(req, firstText) {
  const id = req.body?.sessionId
  if (id) {
    const s = sessions.get(req.userId, id)
    if (s) return { ...s, userId: req.userId }
  }
  return { ...sessions.create(req.userId, titleFrom(firstText)), userId: req.userId }
}

// ---------------------------------------------------------------- admin (emails in ADMIN_EMAILS)
const adminCache = new Map()   // userId -> { admin, at }
async function isAdmin(userId) {
  const hit = adminCache.get(userId)
  if (hit && Date.now() - hit.at < 10 * 60_000) return hit.admin
  let admin = false
  try {
    const u = await clerkClient.users.getUser(userId)
    admin = (u.emailAddresses || []).some((e) => ADMINS.has(String(e.emailAddress).toLowerCase())
      && (e.verification?.status ?? 'verified') === 'verified')
  } catch { admin = false }
  adminCache.set(userId, { admin, at: Date.now() })
  return admin
}
const requireAdmin = async (req, res, next) => {
  if (!(await isAdmin(req.userId))) return res.status(403).json({ error: 'Admins only.' })
  next()
}

app.get('/api/admin/me', requireUser, async (req, res) => res.json({ admin: await isAdmin(req.userId) }))

// forward admin reads/reviews to the engine's log (covers Telegram, WhatsApp and web)
async function forward(req, res, path, init = {}) {
  try {
    const r = await engine(path, init)
    const body = await r.json().catch(() => ({}))
    res.status(r.status).json(r.ok ? body : { error: body.detail || 'The engine could not answer.' })
  } catch {
    res.status(503).json({ error: 'Kasafi engine is offline. Start it, then refresh.' })
  }
}
app.get('/api/admin/stats', requireUser, requireAdmin, (req, res) => forward(req, res, '/api/admin/stats'))
app.get('/api/admin/interactions', requireUser, requireAdmin, (req, res) => {
  const q = new URLSearchParams()
  for (const k of ['channel', 'view', 'q', 'limit', 'offset']) if (req.query[k]) q.set(k, String(req.query[k]))
  forward(req, res, `/api/admin/interactions?${q}`)
})
app.get('/api/admin/interactions/:id', requireUser, requireAdmin, (req, res) =>
  forward(req, res, `/api/admin/interactions/${Number(req.params.id)}`))
app.post('/api/admin/interactions/:id/review', requireUser, requireAdmin, (req, res) =>
  forward(req, res, `/api/admin/interactions/${Number(req.params.id)}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: String(req.body?.status || ''), note: String(req.body?.note || '') }) }))

// ---------------------------------------------------------------- profile
app.get('/api/me', requireUser, async (req, res) => {
  const profile = profiles.get(req.userId)
  let suggested = {}
  if (!profile) {
    try {
      const u = await clerkClient.users.getUser(req.userId)
      suggested = { name: [u.firstName, u.lastName].filter(Boolean).join(' '),
        email: u.primaryEmailAddress?.emailAddress || u.emailAddresses?.[0]?.emailAddress }
    } catch { /* suggestions are optional */ }
  }
  res.json({ profile, suggested })
})

app.put('/api/me', requireUser, async (req, res) => {
  const name = String(req.body?.name || '').replace(/\s+/g, ' ').trim().slice(0, 60)
  const organization = String(req.body?.organization || '').replace(/\s+/g, ' ').trim().slice(0, 120)
  if (name.length < 2) return res.status(400).json({ error: 'Enter your name.' })
  if (!organization) return res.status(400).json({ error: 'Enter your organisation, or None.' })
  let email = null
  try { const u = await clerkClient.users.getUser(req.userId); email = u.primaryEmailAddress?.emailAddress || null } catch { /* optional */ }
  profiles.upsert(req.userId, { name, organization, email })
  res.json({ profile: profiles.get(req.userId) })
})

// ---------------------------------------------------------------- chat history
app.get('/api/sessions', requireUser, (req, res) => res.json({ sessions: sessions.list(req.userId) }))

app.get('/api/sessions/:id', requireUser, (req, res) => {
  const s = sessions.get(req.userId, req.params.id)
  if (!s) return res.status(404).json({ error: 'Chat not found.' })
  res.json({ session: s, messages: messages.list(s.id) })
})

app.patch('/api/sessions/:id', requireUser, (req, res) => {
  const title = titleFrom(req.body?.title)
  if (!sessions.rename(req.userId, req.params.id, title)) return res.status(404).json({ error: 'Chat not found.' })
  res.json({ session: sessions.get(req.userId, req.params.id) })
})

app.delete('/api/sessions/:id', requireUser, (req, res) => {
  if (!sessions.remove(req.userId, req.params.id)) return res.status(404).json({ error: 'Chat not found.' })
  res.json({ ok: true })
})

// ---------------------------------------------------------------- ask (text / voice) -> event stream
app.post('/api/ask', requireUser, requireProfile, askLimit, async (req, res) => {
  const text = String(req.body?.text || '').trim().slice(0, 1000)
  if (!text) return res.status(400).json({ error: 'Type a question first.' })
  const session = sessionFor(req, text)
  const userMsg = messages.add(session.id, { role: 'user', content: text })
  let er
  try {
    er = await engine('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: req.userId, text, name: req.profile.name, organization: req.profile.organization }) })
  } catch { er = { ok: false, status: 503 } }
  await relay(res, er, { session, userMsg })
})

app.post('/api/voice', requireUser, requireProfile, askLimit, upload.single('audio'), async (req, res) => {
  if (!req.file?.buffer?.length) return res.status(400).json({ error: 'The recording was empty. Hold the mic and speak.' })
  const session = sessionFor(req, 'Sakon murya')
  const userMsg = messages.add(session.id, { role: 'user', content: '…', input_type: 'voice' })
  const form = new FormData()
  form.append('audio', new Blob([req.file.buffer], { type: req.file.mimetype || 'audio/webm' }), req.file.originalname || 'voice.webm')
  form.append('user_id', req.userId); form.append('name', req.profile.name); form.append('organization', req.profile.organization)
  let er
  try { er = await engine('/api/voice', { method: 'POST', body: form }) } catch { er = { ok: false, status: 503 } }
  await relay(res, er, { session, userMsg })
})

// ---------------------------------------------------------------- voice reply + feedback
app.post('/api/messages/:id/speak', requireUser, async (req, res) => {
  const m = messages.owned(req.userId, Number(req.params.id))
  if (!m || m.role !== 'assistant') return res.status(404).json({ error: 'Answer not found.' })
  const file = path.join(AUDIO_DIR, `${m.id}.mp3`)
  if (!fs.existsSync(file)) {
    try {
      const r = await engine('/api/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interaction_id: m.interaction_id || 0, text: m.content, lang: m.lang || 'ha' }) })
      if (!r.ok) return res.status(502).json({ error: 'The voice reply could not be made. Try again.' })
      fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()))
    } catch { return res.status(503).json({ error: 'Kasafi engine is offline. Try again in a minute.' }) }
  }
  res.type('audio/mpeg').sendFile(file)
})

app.post('/api/messages/:id/feedback', requireUser, async (req, res) => {
  const m = messages.owned(req.userId, Number(req.params.id))
  if (!m) return res.status(404).json({ error: 'Answer not found.' })
  const value = Number(req.body?.value) > 0 ? 1 : -1
  messages.update(m.id, { feedback: value })
  if (m.interaction_id) {
    engine('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interaction_id: m.interaction_id, value }) }).catch(() => {})
  }
  res.json({ ok: true, feedback: value })
})

app.get('/api/health', async (_req, res) => {
  try { const r = await engine('/api/health'); res.json({ web: true, engine: r.ok ? await r.json() : null }) }
  catch { res.json({ web: true, engine: null }) }
})

// ---------------------------------------------------------------- the React app
const dist = path.resolve(CLIENT_DIST)
if (fs.existsSync(dist)) {
  app.use(express.static(dist, { index: false, maxAge: '1h' }))
  app.get(/^(?!\/api\/).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')))
}

app.listen(PORT, () => console.log(`Kasafi web server on http://localhost:${PORT} (engine: ${ENGINE_URL || 'not set'})`))
