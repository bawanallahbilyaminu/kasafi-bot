import { useEffect, useRef, useState } from 'react'
import { useDispatch } from 'react-redux'
import { sendFeedback } from '../store/chatSlice'
import { apiBlob } from '../lib/api'
import AnswerText from './AnswerText'

let playing = null   // one voice reply at a time

function VoiceButton({ id }) {
  const [state, setState] = useState('idle') // idle | loading | playing | error
  const audio = useRef(null)
  useEffect(() => () => { audio.current?.pause() }, [])

  const toggle = async () => {
    if (state === 'playing') { audio.current.pause(); setState('idle'); return }
    try {
      if (!audio.current) {
        setState('loading')
        const blob = await apiBlob(`/api/messages/${id}/speak`)
        const a = new Audio(URL.createObjectURL(blob))
        a.onended = () => setState('idle')
        a.onpause = () => setState((s) => (s === 'playing' ? 'idle' : s))
        audio.current = a
      }
      if (playing && playing !== audio.current) playing.pause()
      playing = audio.current
      await audio.current.play()
      setState('playing')
    } catch {
      setState('error')
    }
  }
  const label = { idle: 'Saurara', loading: 'Ana shiryawa…', playing: 'Dakata', error: 'Sake gwadawa' }[state]
  return (
    <button onClick={toggle} disabled={state === 'loading'}
      className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-sm font-medium hover:border-gold hover:bg-gold/10 disabled:opacity-60">
      {state === 'playing' ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><rect x="6" y="5" width="4" height="14" /><rect x="14" y="5" width="4" height="14" /></svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" /></svg>
      )}
      {label}
    </button>
  )
}

function Thumb({ up, active, onClick }) {
  return (
    <button onClick={onClick} aria-pressed={active} aria-label={up ? 'Ya taimaka' : 'Bai taimaka ba'} title={up ? 'Ya taimaka' : 'Bai taimaka ba'}
      className={`rounded-full p-1.5 ${active ? (up ? 'bg-green-soft text-green' : 'bg-danger/10 text-danger') : 'text-ink-soft hover:text-ink'}`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden
        style={up ? undefined : { transform: 'rotate(180deg)' }}>
        <path d="M7 11v9H4v-9h3Zm0 0 4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7" />
      </svg>
    </button>
  )
}

export default function Message({ m }) {
  const dispatch = useDispatch()
  const [copied, setCopied] = useState(false)
  if (m.role === 'user') {
    return (
      <div className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-paper">
        {m.input_type === 'voice' && <span className="mr-2" aria-label="Sakon murya">🎙️</span>}
        {m.content === '…' ? <span className="opacity-70">Sakon murya</span> : m.content}
      </div>
    )
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* ignore */ }
  }
  return (
    <div className="flex gap-3">
      <img src="/kasafi-avatar.png" alt="" className="mt-1 h-8 w-8 shrink-0 rounded-full" />
      <div className="min-w-0 flex-1">
        <AnswerText text={m.content} />
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {(m.lang || 'ha') === 'ha' && m.voice ? <VoiceButton id={m.id} /> : null}
          <Thumb up active={m.feedback === 1} onClick={() => dispatch(sendFeedback({ id: m.id, value: 1 }))} />
          <Thumb active={m.feedback === -1} onClick={() => dispatch(sendFeedback({ id: m.id, value: -1 }))} />
          <button onClick={copy} className="rounded-full px-2 py-1 text-sm text-ink-soft hover:text-ink">{copied ? 'An kwafa' : 'Kwafa'}</button>
        </div>
      </div>
    </div>
  )
}
