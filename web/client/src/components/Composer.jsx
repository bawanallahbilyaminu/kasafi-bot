import { useCallback, useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { ask } from '../store/chatSlice'
import useRecorder from '../lib/useRecorder'

const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function Composer() {
  const dispatch = useDispatch()
  const pending = useSelector((s) => s.chat.pending)
  const [text, setText] = useState('')
  const box = useRef(null)
  const onDone = useCallback((audio) => dispatch(ask({ audio })), [dispatch])
  const { recording, seconds, levels, error, start, stop, clearError } = useRecorder({ onDone })

  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [text])

  const send = () => {
    const t = text.trim()
    if (!t || pending) return
    dispatch(ask({ text: t }))
    setText('')
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-2">
      {error && (
        <p className="mb-2 flex items-start justify-between gap-3 rounded-lg bg-surface px-3 py-2 text-sm text-danger" role="alert">
          {error}
          <button onClick={clearError} className="text-ink-soft" aria-label="Rufe">✕</button>
        </p>
      )}
      <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-sm focus-within:border-green">
        {recording ? (
          <div className="flex min-h-[48px] flex-1 items-center gap-3 px-3" aria-live="polite">
            <div className="flex h-8 items-center gap-1" aria-hidden>
              {levels.map((l, i) => (
                <span key={i} className="w-1.5 rounded-full bg-gold" style={{ height: `${Math.round(l * 32)}px` }} />
              ))}
            </div>
            <span className="font-medium tabular-nums">{fmt(seconds)}</span>
            <span className="text-ink-soft">Ina saurare… danna don aikawa</span>
            <button onClick={() => stop(false)} className="ml-auto rounded-lg px-3 py-1.5 text-ink-soft hover:bg-paper">Soke</button>
          </div>
        ) : (
          <textarea ref={box} rows={1} value={text} onChange={(e) => setText(e.target.value)} disabled={!!pending}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Rubuta tambayarka, ko danna makirufo ka yi magana…" aria-label="Tambaya"
            className="max-h-[180px] min-h-[48px] flex-1 resize-none bg-transparent px-3 py-3 outline-none placeholder:text-ink-soft disabled:opacity-60" />
        )}

        {!recording && text.trim() ? (
          <button onClick={send} disabled={!!pending} aria-label="Aika"
            className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-green text-white disabled:opacity-50">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
        ) : (
          <button onClick={() => (recording ? stop(true) : start())} disabled={!!pending && !recording}
            aria-label={recording ? 'Aika sakon murya' : 'Yi magana'} aria-pressed={recording}
            className={`grid h-14 w-14 shrink-0 place-items-center rounded-full text-ink shadow-md transition disabled:opacity-50 ${recording ? 'bg-gold ring-4 ring-gold/30' : 'bg-gold hover:brightness-105'}`}>
            {recording ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2.4" fill="none" /></svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
                <rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </svg>
            )}
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-ink-soft">
        Amsoshi daga kasafin 2025 da 2026 da rahotannin aiwatarwa. Duba shafin madogara kafin amfani da adadi a hukumance.
      </p>
    </div>
  )
}
