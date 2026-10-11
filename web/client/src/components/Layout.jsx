import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchSessions, newChat, openSession } from '../store/chatSlice'
import Sidebar from './Sidebar'
import ChatView from './ChatView'

export default function Layout() {
  const { id } = useParams()
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { currentId, pending, sessionsLoaded } = useSelector((s) => s.chat)
  const [drawer, setDrawer] = useState(false)

  useEffect(() => { if (!sessionsLoaded) dispatch(fetchSessions()) }, [dispatch, sessionsLoaded])

  // URL -> state: open the chat in the address bar (unless it is the one we're already in)
  useEffect(() => {
    if (id && id !== currentId && !pending) dispatch(openSession(id))
    if (!id && currentId && !pending) dispatch(newChat())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // state -> URL: a new chat got its id from the server
  useEffect(() => {
    if (currentId && currentId !== id) navigate(`/c/${currentId}`, { replace: !id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId])

  return (
    <div className="flex h-full">
      <Sidebar open={drawer} onClose={() => setDrawer(false)} />
      <ChatView onMenu={() => setDrawer(true)} />
    </div>
  )
}
