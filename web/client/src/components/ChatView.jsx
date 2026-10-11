import { useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { ask, dismissError } from '../store/chatSlice'
import Message from './Message'
import Composer from './Composer'

const EXAMPLES = [
  'Nawa aka ware wa lafiya a 2026?',
  'Nawa aka kashe a fannin ilimi a 2025?',
  'Wadanne ayyuka ne za a yi a Tambuwal?',
  'Ayyuka nawa aka fara a 2025 kuma suke ci gaba a 2026?',
  'Wace ma’aikata ce ta fi karancin aiwatar da kasafin 2025?',
  'How much revenue did the state receive in 2025?',
]
const STEPS = [
  ['listen', 'Ina sauraron sakon muryarku'],
  ['understand', 'Ina fahimtar tambayar (N-ATLaS)'],
  ['search', 'Ina duba kasafin kudi'],
  ['write', 'Ina rubuta amsa (N-ATLaS)'],
]

function Progress({ pending }) {
  const at = STEPS.findIndex(([k]) => k === pending.stage)
  const steps = STEPS.filter(([k]) => k !== 'listen' || pending.input === 'voice')
  return (
    <div className="flex gap-3" aria-live="polite">
      <img src="/kasafi-avatar.png" alt="" className="mt-1 h-8 w-8 shrink-0 rounded-full" />
      <ol className="space-y-1.5 pt-1">
        {steps.map(([k, label]) => {
          const i = STEPS.findIndex(([x]) => x === k)
          const state = i < at ? 'done' : i === at ? 'now' : 'next'
          if (state === 'next') return null
          return (
            <li key={k} className={`flex items-center gap-2 ${state === 'done' ? 'text-ink-soft' : 'font-medium'}`}>
              {state === 'done' ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2.6" aria-hidden><path d="m5 12 5 5 9-10" /></svg>
              ) : (
                <span className="stage-dot inline-block h-2.5 w-2.5 rounded-full bg-gold" aria-hidden />
              )}
              {label}{state === 'now' ? '…' : ''}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export default function ChatView({ onMenu }) {
  const dispatch = useDispatch()
  const { messages, pending, error, loadingSession, currentId, sessions } = useSelector((s) => s.chat)
  const name = useSelector((s) => s.profile.profile?.name?.split(' ')[0])
  const end = useRef(null)
  const title = sessions.find((s) => s.id === currentId)?.title

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length, pending?.stage, pending?.heard])

  const empty = !messages.length && !pending && !loadingSession

  return (
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2.5 md:px-6">
        <button onClick={onMenu} className="rounded-lg p-2 hover:bg-surface md:hidden" aria-label="Bude jerin tattaunawa">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <h1 className="truncate font-medium">{title || 'Sabuwar tattaunawa'}</h1>
      </header>

      <div className="flex-1 overflow-y-auto">
        {empty ? (
          <div className="mx-auto flex h-full max-w-3xl flex-col justify-center px-5 py-10">
            <h2 className="text-3xl font-bold leading-tight md:text-4xl">Sannu{name ? `, ${name}` : ''}. Me kuke so ku sani game da kasafin Sokoto?</h2>
            <p className="mt-3 text-ink-soft">Ku danna makirufo ku yi tambaya da Hausa, ko ku rubuta. Ga wasu misalai:</p>
            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map((q) => (
                <button key={q} onClick={() => dispatch(ask({ text: q }))}
                  className="rounded-xl border border-line bg-surface px-4 py-3 text-left hover:border-green">
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 md:px-6">
            {loadingSession && <p className="text-ink-soft">Ana budewa…</p>}
            {messages.map((m) => <Message key={m.id} m={m} />)}
            {pending && !pending.metaReceived && (
              <Message m={{ id: 'pending', role: 'user', content: pending.input === 'voice' ? '…' : pending.text, input_type: pending.input }} />
            )}
            {pending && <Progress pending={pending} />}
            <div ref={end} />
          </div>
        )}
      </div>

      {error && (
        <div className="mx-auto w-full max-w-3xl px-4">
          <p className="flex items-start justify-between gap-3 rounded-lg border border-danger/30 bg-surface px-3 py-2 text-sm text-danger" role="alert">
            {error}
            <button onClick={() => dispatch(dismissError())} className="text-ink-soft" aria-label="Rufe">✕</button>
          </p>
        </div>
      )}
      <Composer />
    </main>
  )
}
