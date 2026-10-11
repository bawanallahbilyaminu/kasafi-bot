import { SignInButton, SignUpButton } from '@clerk/react'
import AnswerText from './AnswerText'

const SAMPLE_Q = 'Nawa aka ware wa ma’aikatar lafiya a 2026?'
const SAMPLE_A = 'An ware wa Ma’aikatar Lafiya ₦124.41 biliyan a kasafin 2026. Zuwa watan Yuni, an kashe kashi 10.6 cikin 100 na kudin.\n\n📄 Madogara: Kasafin Kudin Jihar Sokoto na 2026, shafi 18; Rahoton aiwatar da kasafi, Q2 2026'

export default function Landing() {
  return (
    <div className="min-h-full bg-paper">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <div className="flex items-center gap-3">
          <img src="/kasafi-avatar.png" alt="" className="h-9 w-9 rounded-full" />
          <span className="text-lg font-bold">Kasafi AI</span>
        </div>
        <SignInButton mode="modal">
          <button className="rounded-lg px-4 py-2 font-medium text-ink hover:bg-green-soft">Shiga</button>
        </SignInButton>
      </header>

      <main className="mx-auto grid max-w-6xl gap-12 px-5 pb-16 pt-6 md:grid-cols-[1.05fr_1fr] md:items-center md:pt-16">
        <section>
          <h1 className="text-[2.6rem] font-bold leading-[1.08] tracking-tight md:text-[3.4rem]">
            Tambayi kasafin kudin Jihar Sokoto.
          </h1>
          <p className="mt-5 max-w-[34rem] text-lg text-ink-soft">
            Rubuta ko yi magana da Hausa. Kasafi yana amsa daga takardun gwamnati kai tsaye, da adadin kudi da
            shafin da ya fito.
          </p>
          <p className="mt-2 max-w-[34rem] text-ink-soft">
            Ask about the 2025 and 2026 budgets and how they were spent, in Hausa or English, by text or voice.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <SignUpButton mode="modal">
              <button className="rounded-xl bg-green px-6 py-3 text-lg font-bold text-white shadow-sm hover:brightness-110">
                Fara yanzu
              </button>
            </SignUpButton>
            <SignInButton mode="modal">
              <button className="rounded-xl border border-line px-6 py-3 text-lg font-medium hover:bg-surface">
                Ina da asusu
              </button>
            </SignInButton>
          </div>
          <p className="mt-4 text-sm text-ink-soft">Shiga da Google ko imel. Kyauta ne.</p>
        </section>

        <section aria-label="Misalin tambaya da amsa" className="rounded-3xl border border-line bg-surface p-5 md:p-7">
          <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-3 text-paper">
            <span className="mr-2" aria-hidden>🎙️</span>{SAMPLE_Q}
          </div>
          <div className="mt-5 flex gap-3">
            <img src="/kasafi-avatar.png" alt="" className="mt-1 h-8 w-8 shrink-0 rounded-full" />
            <AnswerText text={SAMPLE_A} />
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-5 pb-8 text-sm text-ink-soft">
        Halal Numeriq Limited, Sokoto. N-ATLaS da Hausa-ASR ne ke sarrafa harshe da murya: powered by Awarri
        Technologies in an initiative of the Federal Ministry of Communications, Innovation and Digital Economy.
      </footer>
    </div>
  )
}
