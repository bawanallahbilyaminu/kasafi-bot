import { useState } from 'react'
import { UserButton } from '@clerk/react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { deleteSession, newChat, renameSession } from '../store/chatSlice'
import { startEditing } from '../store/profileSlice'

function groupOf(iso) {
  const d = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T') + 'Z')
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000)
  return days <= 0 ? 'Yau' : days === 1 ? 'Jiya' : days < 7 ? 'Wannan makon' : 'Kwanakin baya'
}

function Row({ s, active, onPick }) {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(s.title)
  const save = () => {
    setEditing(false)
    if (title.trim() && title !== s.title) dispatch(renameSession({ id: s.id, title }))
  }
  const remove = () => {
    if (window.confirm(`Goge "${s.title}"? Ba za a iya dawo da ita ba.`)) {
      dispatch(deleteSession(s.id))
      if (active) navigate('/')
    }
  }
  if (editing) {
    return (
      <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { setTitle(s.title); setEditing(false) } }}
        className="w-full rounded-lg border border-green bg-paper px-3 py-2 text-[15px] outline-none" aria-label="Sunan tattaunawa" />
    )
  }
  return (
    <div className={`group flex items-center rounded-lg ${active ? 'bg-green-soft' : 'hover:bg-paper'}`}>
      <button onClick={onPick} className="min-w-0 flex-1 truncate px-3 py-2 text-left text-[15px]" title={s.title}>
        {s.title}
      </button>
      <div className={`flex shrink-0 pr-1 ${active ? '' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'}`}>
        <button onClick={() => setEditing(true)} className="rounded p-1.5 text-ink-soft hover:text-ink" aria-label="Canza suna" title="Canza suna">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
        </button>
        <button onClick={remove} className="rounded p-1.5 text-ink-soft hover:text-danger" aria-label="Goge" title="Goge">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /></svg>
        </button>
      </div>
    </div>
  )
}

export default function Sidebar({ open, onClose }) {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { sessions, currentId, pending } = useSelector((s) => s.chat)
  const profile = useSelector((s) => s.profile.profile)

  const groups = []
  for (const s of sessions) {
    const g = groupOf(s.updated_at || s.created_at || new Date().toISOString())
    const last = groups[groups.length - 1]
    if (last && last.name === g) last.items.push(s)
    else groups.push({ name: g, items: [s] })
  }
  const go = (path) => { navigate(path); onClose() }

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-ink/30 md:hidden" onClick={onClose} aria-hidden />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-surface transition-transform md:static md:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Tattaunawa">
        <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
          <img src="/kasafi-avatar.png" alt="" className="h-8 w-8 rounded-full" />
          <span className="text-lg font-bold">Kasafi AI</span>
        </div>
        <div className="px-3">
          <button disabled={!!pending} onClick={() => { dispatch(newChat()); go('/') }}
            className="flex w-full items-center gap-2 rounded-lg border border-line px-3 py-2.5 font-medium hover:bg-paper disabled:opacity-50">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
            Sabuwar tattaunawa
          </button>
        </div>
        <nav className="mt-3 flex-1 overflow-y-auto px-3 pb-3">
          {!sessions.length && <p className="px-3 py-2 text-sm text-ink-soft">Tattaunawarku za ta bayyana a nan.</p>}
          {groups.map((g) => (
            <div key={g.name} className="mb-3">
              <p className="px-3 pb-1 pt-2 text-sm font-medium text-ink-soft">{g.name}</p>
              {g.items.map((s) => (
                <Row key={s.id} s={s} active={s.id === currentId} onPick={() => !pending && go(`/c/${s.id}`)} />
              ))}
            </div>
          ))}
        </nav>
        <div className="flex items-center gap-3 border-t border-line px-4 py-3">
          <UserButton />
          <button onClick={() => dispatch(startEditing())} className="min-w-0 flex-1 text-left" title="Canza bayananku">
            <span className="block truncate font-medium">{profile?.name}</span>
            <span className="block truncate text-sm text-ink-soft">{profile?.organization}</span>
          </button>
        </div>
      </aside>
    </>
  )
}
