import { useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { saveProfile, stopEditing } from '../store/profileSlice'

const ORGS = ['Ma’aikatar Kasafi (MBEP)', 'Abokin ci gaba (Development partner)', 'Kungiyar farar hula (CSO)',
  'Dalibi (Student)', 'Babu (None)']

export default function Onboarding() {
  const dispatch = useDispatch()
  const { profile, suggested, saving, error, status } = useSelector((s) => s.profile)
  const first = status === 'missing'
  const [name, setName] = useState(profile?.name || suggested?.name || '')
  const [org, setOrg] = useState(profile?.organization || '')
  const nameRef = useRef(null)
  useEffect(() => { nameRef.current?.focus() }, [])

  const submit = (e) => {
    e.preventDefault()
    dispatch(saveProfile({ name, organization: org }))
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-labelledby="ob-title">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl">
        <h2 id="ob-title" className="text-2xl font-bold">{first ? 'Barka da zuwa!' : 'Bayananka'}</h2>
        <p className="mt-1 text-ink-soft">
          {first ? 'Kafin mu fara, gaya mana sunanka da inda kake aiki. Yana taimaka mana mu inganta Kasafi.'
            : 'Sabunta sunanka ko kungiyarka.'}
        </p>

        <label className="mt-5 block font-medium" htmlFor="ob-name">Suna <span className="font-normal text-ink-soft">(Name)</span></label>
        <input id="ob-name" ref={nameRef} value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
          autoComplete="name" required
          className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2.5 outline-none focus:border-green" />

        <label className="mt-4 block font-medium" htmlFor="ob-org">
          Ma’aikata, hukuma ko kungiya <span className="font-normal text-ink-soft">(Organisation)</span>
        </label>
        <input id="ob-org" value={org} onChange={(e) => setOrg(e.target.value)} maxLength={120} required
          placeholder="misali: UNICEF, Jami’ar Usmanu Danfodiyo"
          className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2.5 outline-none focus:border-green" />
        <div className="mt-2 flex flex-wrap gap-2">
          {ORGS.map((o) => (
            <button type="button" key={o} onClick={() => setOrg(o)}
              className={`rounded-full border px-3 py-1 text-sm ${org === o ? 'border-green bg-green-soft' : 'border-line hover:bg-paper'}`}>
              {o}
            </button>
          ))}
        </div>

        {error && <p className="mt-3 text-sm text-danger" role="alert">{error}</p>}
        <p className="mt-4 text-sm text-ink-soft">
          Muna adana sunanka, kungiyarka da tambayoyinka domin inganta Kasafi. Ba ma raba su da kowa.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          {!first && (
            <button type="button" onClick={() => dispatch(stopEditing())} className="rounded-lg px-4 py-2 hover:bg-paper">
              Soke
            </button>
          )}
          <button type="submit" disabled={saving}
            className="rounded-lg bg-green px-5 py-2 font-bold text-white disabled:opacity-60">
            {saving ? 'Ana adanawa…' : first ? 'Ci gaba' : 'Adana'}
          </button>
        </div>
      </form>
    </div>
  )
}
