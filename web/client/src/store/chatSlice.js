import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import { api, stream } from '../lib/api'

export const fetchSessions = createAsyncThunk('chat/sessions', () => api('/api/sessions'))
export const openSession = createAsyncThunk('chat/open', (id) => api(`/api/sessions/${id}`))
export const renameSession = createAsyncThunk('chat/rename', ({ id, title }) =>
  api(`/api/sessions/${id}`, { method: 'PATCH', body: { title } }))
export const deleteSession = createAsyncThunk('chat/delete', async (id) => {
  await api(`/api/sessions/${id}`, { method: 'DELETE' })
  return id
})
export const sendFeedback = createAsyncThunk('chat/feedback', ({ id, value }) =>
  api(`/api/messages/${id}/feedback`, { method: 'POST', body: { value } }).then((r) => ({ id, feedback: r.feedback })))

// Ask by text ({ text }) or voice ({ audio: Blob }). The server streams: meta -> stage* -> answer | error.
export const ask = createAsyncThunk('chat/ask', async ({ text, audio }, { getState, dispatch, rejectWithValue }) => {
  const sessionId = getState().chat.currentId
  let form
  if (audio) {
    form = new FormData()
    const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm'
    form.append('audio', audio, `voice.${ext}`)
    if (sessionId) form.append('sessionId', sessionId)
  }
  try {
    await stream(audio ? '/api/voice' : '/api/ask', audio ? { form } : { json: { text, sessionId } }, (event, data) => {
      if (event === 'meta') dispatch(slice.actions.meta(data))
      else if (event === 'stage') dispatch(slice.actions.stage(data))
      else if (event === 'answer') dispatch(slice.actions.answer(data))
      else if (event === 'error') dispatch(slice.actions.streamError(data.message))
    })
  } catch (e) {
    return rejectWithValue(e.message)
  }
})

const slice = createSlice({
  name: 'chat',
  initialState: {
    sessions: [],
    sessionsLoaded: false,
    currentId: null,
    messages: [],
    loadingSession: false,
    pending: null, // { input: 'text'|'voice', text, stage, heard }
    error: null,
  },
  reducers: {
    newChat: (s) => { s.currentId = null; s.messages = []; s.error = null },
    dismissError: (s) => { s.error = null },
    meta: (s, { payload }) => {
      const { session, userMessage } = payload
      if (!s.sessions.some((x) => x.id === session.id)) s.sessions.unshift(session)
      s.currentId = session.id
      if (userMessage) s.messages.push(userMessage)
      if (s.pending) s.pending.metaReceived = true
    },
    stage: (s, { payload }) => {
      if (!s.pending) return
      if (payload.stage === 'heard') {
        s.pending.heard = payload.text
        const last = s.messages[s.messages.length - 1]
        if (last && last.role === 'user' && last.input_type === 'voice') { last.content = payload.text; last.transcript = payload.text }
      } else {
        s.pending.stage = payload.stage
      }
    },
    answer: (s, { payload }) => {
      s.messages.push(payload.message)
      const i = s.sessions.findIndex((x) => x.id === payload.session.id)
      if (i >= 0) {
        const [row] = s.sessions.splice(i, 1)
        s.sessions.unshift({ ...row, title: payload.session.title || row.title, updated_at: new Date().toISOString() })
      }
      s.pending = null
    },
    streamError: (s, { payload }) => { s.error = payload; s.pending = null },
  },
  extraReducers: (b) => {
    b.addCase(fetchSessions.fulfilled, (s, a) => { s.sessions = a.payload.sessions; s.sessionsLoaded = true })
      .addCase(openSession.pending, (s, a) => { s.loadingSession = true; s.currentId = a.meta.arg; s.error = null })
      .addCase(openSession.fulfilled, (s, a) => {
        s.loadingSession = false
        if (s.currentId === a.payload.session.id) s.messages = a.payload.messages
      })
      .addCase(openSession.rejected, (s, a) => { s.loadingSession = false; s.currentId = null; s.messages = []; s.error = a.error.message })
      .addCase(renameSession.fulfilled, (s, a) => {
        const row = s.sessions.find((x) => x.id === a.payload.session.id)
        if (row) row.title = a.payload.session.title
      })
      .addCase(deleteSession.fulfilled, (s, a) => {
        s.sessions = s.sessions.filter((x) => x.id !== a.payload)
        if (s.currentId === a.payload) { s.currentId = null; s.messages = [] }
      })
      .addCase(sendFeedback.fulfilled, (s, a) => {
        const m = s.messages.find((x) => x.id === a.payload.id)
        if (m) m.feedback = a.payload.feedback
      })
      .addCase(ask.pending, (s, a) => {
        s.error = null
        s.pending = { input: a.meta.arg.audio ? 'voice' : 'text', text: a.meta.arg.text || '', stage: a.meta.arg.audio ? 'listen' : 'understand', heard: null }
      })
      .addCase(ask.fulfilled, (s) => { if (s.pending) { s.pending = null; s.error = s.error || 'No answer came back. Try again.' } })
      .addCase(ask.rejected, (s, a) => { s.pending = null; s.error = a.payload || a.error.message })
  },
})

export const { newChat, dismissError } = slice.actions
export default slice.reducer
