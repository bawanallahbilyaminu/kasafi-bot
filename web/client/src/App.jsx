import { useEffect } from 'react'
import { useAuth } from '@clerk/react'
import { useDispatch, useSelector } from 'react-redux'
import { Route, Routes } from 'react-router-dom'
import { setTokenGetter } from './lib/api'
import { fetchProfile } from './store/profileSlice'
import Landing from './components/Landing'
import Onboarding from './components/Onboarding'
import Layout from './components/Layout'

function Splash({ text = 'Ana budewa…' }) {
  return (
    <div className="grid h-full place-items-center text-ink-soft">
      <div className="flex items-center gap-3">
        <img src="/kasafi-avatar.png" alt="" className="h-10 w-10 rounded-full" />
        <span>{text}</span>
      </div>
    </div>
  )
}

function SignedInApp() {
  const { getToken } = useAuth()
  const dispatch = useDispatch()
  const { status, editing } = useSelector((s) => s.profile)

  useEffect(() => {
    setTokenGetter(() => getToken())
    dispatch(fetchProfile())
  }, [dispatch, getToken])

  if (status === 'idle' || status === 'loading') return <Splash />
  if (status === 'error') return <Splash text="Could not reach Kasafi. Refresh the page to try again." />
  return (
    <>
      <Routes>
        <Route path="/c/:id" element={<Layout />} />
        <Route path="*" element={<Layout />} />
      </Routes>
      {(status === 'missing' || editing) && <Onboarding />}
    </>
  )
}

export default function App() {
  const { isLoaded, isSignedIn } = useAuth()
  if (!isLoaded) return <Splash />
  return isSignedIn ? <SignedInApp /> : <Landing />
}
