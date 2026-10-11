// Admin review: every interaction from Telegram, WhatsApp and the web, with what N-ATLaS understood, the facts it
// was given, the answer, and why a check stepped in. Mark each one OK / Issue / Fixed with a note.
import { useCallback, useEffect, useState } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import AnswerText from './AnswerText'

const VIEWS = [
  ['all', 'All'],
  ['problems', 'Problems'],
  ['unreviewed', 'Unreviewed problems'],
  ['down', '👎 Feedback'],
  ['issues', 'Marked issue'],
  ['voice', 'Voice'],
]
const CHANNELS = [['', 'All channels'], ['telegram', 'Telegram'], ['whatsapp', 'WhatsApp'], ['web', 'Web']]
const PAGE = 50

const when = (ts) => {
  if (!ts) return ''
  const d = new Date(ts.endsWith('Z') || ts.includes('+') ? ts : ts + 'Z')
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : '–')

function Badge({ tone, icon, children, title }) {
  const tones = {
    good: 'border-green/40 text-green',
    warn: 'border-gold/60 text-gold-deep',
    bad: 'border-danger/50 text-danger',
    plain: 'border-line text-ink-soft',
  }
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      <span aria-hidden>{icon}</span>{children}
    </span>
  )
}

function SourceBadge({ r }) {
  if (r.error) return <Badge tone="bad" icon="✕" title={r.error}>Error</Badge>
  if (r.answer_source === 'natlas') return <Badge tone="good" icon="✓">N-ATLaS</Badge>
  if (r.grounding_fail) return <Badge tone="warn" icon="↩" title={r.grounding_fail}>Check stepped in</Badge>
  if (r.answer_source === 'template') return <Badge tone="plain" icon="↩">Template</Badge>
  return <Badge tone="plain" icon="·">{r.answer_source || 'No answer'}</Badge>
}

function ReviewBadge({ status }) {
  if (status === 'ok') return <Badge tone="good" icon="✓">OK</Badge>
  if (status === 'issue') return <Badge tone="bad" icon="!">Issue</Badge>
  if (status === 'fixed') return <Badge tone="plain" icon="✓">Fixed</Badge>
  return null
}

function Tile({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <p className="text-sm text-ink-soft">{label}</p>
      <p className="mt-0.5 text-2xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-ink-soft">{sub}</p>}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="border-t border-line pt-3">
      <h3 className="mb-1.5 text-sm font-bold text-ink-soft">{title}</h3>
      {children}
    </section>
  )
}

function Detail({ id, onClose, onSaved }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let live = true
    setD(null); setErr(null)
    api(`/api/admin/interactions/${id}`).then((r) => { if (live) { setD(r); setNote(r.review_note || '') } })
      .catch((e) => live && setErr(e.message))
    return () => { live = false }
  }, [id])

  const review = async (status) => {
    setSaving(true)
    try {
      const r = await api(`/api/admin/interactions/${id}/review`, { method: 'POST', body: { status, note } })
      setD(r); onSaved(r)
    } catch (e) { setErr(e.message) } finally { setSaving(false) }
  }

  const und = d?.natlas_understanding && typeof d.natlas_understanding === 'object' ? d.natlas_understanding : null
  const ent = d?.entities && typeof d.entities === 'object' ? d.entities : null
  const timings = d ? [['ASR', d.ms_asr], ['Understand', d.ms_understand], ['Retrieve', d.ms_retrieve], ['Write', d.ms_write],
    ['Voice reply', d.ms_tts], ['Total', d.ms_total]].filter(([, v]) => v != null) : []

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="font-bold">Interaction #{id}</h2>
        <button onClick={onClose} className="ml-auto rounded-lg px-3 py-1.5 text-ink-soft hover:bg-paper" aria-label="Close">✕</button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {err && <p className="text-sm text-danger" role="alert">{err}</p>}
        {!d && !err && <p className="text-ink-soft">Loading…</p>}
        {d && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink-soft">
              <span>{when(d.ts_utc)}</span><span>{d.channel}</span><span>{d.input_type === 'voice' ? `voice ${d.audio_seconds ? `${Math.round(d.audio_seconds)}s` : ''}` : 'text'}</span>
              <span className="font-medium text-ink">{d.name || 'Unregistered'}</span>{d.organization && <span>({d.organization})</span>}
              <SourceBadge r={d} />{d.feedback === -1 && <Badge tone="bad" icon="👎">Disliked</Badge>}
              {d.feedback === 1 && <Badge tone="good" icon="👍">Liked</Badge>}<ReviewBadge status={d.review_status} />
            </div>

            <Section title={d.input_type === 'voice' ? 'What Hausa-ASR heard' : 'Question'}>
              <p className="text-lg">{d.transcript || '—'}</p>
            </Section>

            <Section title="How N-ATLaS understood it">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[15px]">
                <dt className="text-ink-soft">English</dt><dd>{d.english || und?.english || '—'}</dd>
                <dt className="text-ink-soft">Wants</dt><dd>{und?.wants || '—'}{und?.topic ? ` · topic: ${und.topic}` : ''}{und?.year ? ` · year: ${und.year}` : ''}</dd>
                <dt className="text-ink-soft">Routed to</dt><dd>{d.intent || '—'}</dd>
                {ent && <><dt className="text-ink-soft">Matched</dt><dd className="break-words text-sm">{JSON.stringify(ent)}</dd></>}
              </dl>
            </Section>

            {(d.grounding_fail || d.error) && (
              <Section title="Why the check stepped in">
                {d.grounding_fail && <p className="text-[15px]">{d.grounding_fail}</p>}
                {d.error && <p className="text-[15px] text-danger">{d.error}</p>}
              </Section>
            )}

            <Section title="Answer sent">
              <AnswerText text={d.answer || '—'} />
            </Section>

            <Section title="Facts given to N-ATLaS">
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-paper p-3 text-sm">{d.facts || '—'}</pre>
            </Section>

            {timings.length > 0 && (
              <Section title="Timings">
                <p className="text-sm tabular-nums text-ink-soft">{timings.map(([k, v]) => `${k} ${(v / 1000).toFixed(1)}s`).join('   ')}</p>
                <p className="mt-1 text-xs text-ink-soft">{[d.asr_model, d.llm_model].filter(Boolean).join(' · ')}</p>
              </Section>
            )}

            <Section title="Your review">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000}
                placeholder="What is wrong, or what you changed"
                className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-[15px] outline-none focus:border-green" />
              <div className="mt-2 flex flex-wrap gap-2">
                <button disabled={saving} onClick={() => review('ok')} className="rounded-lg border border-green/50 px-3 py-1.5 font-medium text-green hover:bg-green-soft disabled:opacity-50">Mark OK</button>
                <button disabled={saving} onClick={() => review('issue')} className="rounded-lg border border-danger/50 px-3 py-1.5 font-medium text-danger hover:bg-danger/10 disabled:opacity-50">Mark issue</button>
                <button disabled={saving} onClick={() => review('fixed')} className="rounded-lg border border-line px-3 py-1.5 font-medium hover:bg-paper disabled:opacity-50">Mark fixed</button>
                {d.review_status && <button disabled={saving} onClick={() => review('')} className="rounded-lg px-3 py-1.5 text-ink-soft hover:bg-paper disabled:opacity-50">Clear</button>}
              </div>
              {d.reviewed_utc && <p className="mt-2 text-xs text-ink-soft">Reviewed {when(d.reviewed_utc)}</p>}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

export default function AdminPage() {
  const navigate = useNavigate()
  const { isAdmin, status } = useSelector((s) => s.profile)
  const [stats, setStats] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [view, setView] = useState('problems')
  const [channel, setChannel] = useState('')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)

  const load = useCallback(async (offset = 0) => {
    setLoading(true); setErr(null)
    try {
      const params = new URLSearchParams({ view, limit: String(PAGE), offset: String(offset) })
      if (channel) params.set('channel', channel)
      if (search) params.set('q', search)
      const [st, list] = await Promise.all([offset ? Promise.resolve(null) : api('/api/admin/stats'),
        api(`/api/admin/interactions?${params}`)])
      if (st) setStats(st)
      setTotal(list.total)
      setRows((prev) => (offset ? [...prev, ...list.rows] : list.rows))
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [view, channel, search])

  useEffect(() => { if (isAdmin) load(0) }, [isAdmin, load])

  if (status === 'ready' && !isAdmin) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div>
          <p className="text-lg font-bold">This page is for Kasafi admins.</p>
          <p className="mt-1 text-ink-soft">Your email is not on the admin list (ADMIN_EMAILS on the server).</p>
          <button onClick={() => navigate('/')} className="mt-4 rounded-lg bg-green px-4 py-2 font-bold text-white">Back to chat</button>
        </div>
      </div>
    )
  }

  const s = stats
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-line px-4 py-3 md:px-6">
        <img src="/kasafi-avatar.png" alt="" className="h-8 w-8 rounded-full" />
        <h1 className="text-lg font-bold">Kasafi admin</h1>
        <button onClick={() => load(0)} disabled={loading} className="ml-auto rounded-lg border border-line px-3 py-1.5 hover:bg-surface disabled:opacity-50">
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
        <button onClick={() => navigate('/')} className="rounded-lg px-3 py-1.5 hover:bg-surface">Back to chat</button>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className={`flex min-w-0 flex-1 flex-col ${selected ? 'hidden lg:flex' : 'flex'}`}>
          <div className="space-y-4 overflow-y-auto px-4 py-4 md:px-6">
            {err && <p className="rounded-lg border border-danger/30 bg-surface px-3 py-2 text-sm text-danger" role="alert">{err}</p>}
            {s && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
                <Tile label="Interactions" value={s.interactions} sub={`${s.today} today · NAIC needs 50`} />
                <Tile label="Registered users" value={s.users} sub={s.registering ? `+${s.registering} registering` : null} />
                <Tile label="Voice notes" value={pct(s.voice, s.interactions)} sub={`${s.voice} of ${s.interactions}`} />
                <Tile label="Written by N-ATLaS" value={pct(s.natlas, s.natlas + s.template)} sub={`${s.template} template answers`} />
                <Tile label="Problems to review" value={s.unreviewed} sub={`${s.problems} problems · ${s.open_issues} open issues`} />
                <Tile label="Feedback" value={`👍 ${s.thumbs_up} · 👎 ${s.thumbs_down}`} sub={s.median_ms ? `median reply ${(s.median_ms / 1000).toFixed(1)}s` : null} />
              </div>
            )}
            {s && (s.orgs?.length > 0 || s.by_channel?.length > 0) && (
              <p className="text-sm text-ink-soft">
                {s.by_channel.map((c) => `${c.k} ${c.n}`).join(' · ')}
                {s.orgs?.length > 0 && <> — organisations: {s.orgs.map((o) => `${o.k} (${o.n})`).join(', ')}</>}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter">
                {VIEWS.map(([k, label]) => (
                  <button key={k} role="tab" aria-selected={view === k} onClick={() => setView(k)}
                    className={`rounded-full border px-3 py-1 text-sm ${view === k ? 'border-green bg-green-soft font-medium' : 'border-line hover:bg-surface'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <select value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="Channel"
                className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm">
                {CHANNELS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
              <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()) }} className="flex min-w-[200px] flex-1 gap-1">
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search questions, answers, names"
                  className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm outline-none focus:border-green" />
                <button className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface">Search</button>
              </form>
            </div>

            <p className="text-sm text-ink-soft">{total} {total === 1 ? 'interaction' : 'interactions'}</p>
            <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
              {rows.map((r) => (
                <li key={r.id}>
                  <button onClick={() => setSelected(r.id)}
                    className={`block w-full px-4 py-3 text-left hover:bg-paper ${selected === r.id ? 'bg-green-soft' : ''}`}>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                      <span className="tabular-nums">#{r.id}</span><span>{when(r.ts_utc)}</span><span>{r.channel}</span>
                      <span>{r.input_type === 'voice' ? '🎙️' : '⌨️'}</span>
                      <span className="font-medium text-ink">{r.name || 'Unregistered'}</span>{r.organization && <span>{r.organization}</span>}
                    </div>
                    <p className="mt-1 line-clamp-2 font-medium">{r.transcript || '—'}</p>
                    <p className="mt-0.5 line-clamp-1 text-sm text-ink-soft">{(r.answer_preview || '').replace(/[*_]/g, '')}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      <SourceBadge r={r} />
                      {r.intent && <Badge tone="plain" icon="›">{r.intent}</Badge>}
                      {r.feedback === -1 && <Badge tone="bad" icon="👎">Disliked</Badge>}
                      {r.feedback === 1 && <Badge tone="good" icon="👍">Liked</Badge>}
                      <ReviewBadge status={r.review_status} />
                    </div>
                  </button>
                </li>
              ))}
              {!rows.length && !loading && <li className="px-4 py-6 text-center text-ink-soft">Nothing here. Try another filter.</li>}
            </ul>
            {rows.length < total && (
              <button onClick={() => load(rows.length)} disabled={loading}
                className="w-full rounded-lg border border-line py-2 hover:bg-surface disabled:opacity-50">Load more</button>
            )}
          </div>
        </div>

        {selected && (
          <aside className="w-full border-l border-line bg-surface lg:w-[46%] lg:max-w-[720px]">
            <Detail id={selected} onClose={() => setSelected(null)}
              onSaved={(d) => setRows((prev) => prev.map((r) => (r.id === d.id ? { ...r, review_status: d.review_status, review_note: d.review_note } : r)))} />
          </aside>
        )}
      </div>
    </div>
  )
}
