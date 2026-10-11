// Renders the bot's answers (written for Telegram: *bold*, _italic_, "•" bullets, a "📄 Madogara" source line).
// Naira figures are emphasised so the number a person asked for is the first thing they see.
const FIGURE = /(₦\s?[\d,]+(?:\.\d+)?(?:\s?(?:tiriliyan|biliyan|miliyan|dubu|trillion|billion|million|bn|m)\b)?|kashi [\d.]+ cikin 100|\b\d+(?:\.\d+)?%)/g
const INLINE = /(\*[^*\n]+\*|_[^_\n]+_)/g

function Figures({ text }) {
  return text.split(FIGURE).map((part, i) => (i % 2 === 1 ? <span key={i} className="figure">{part}</span> : part))
}

function Inline({ text }) {
  return text.split(INLINE).map((part, i) => {
    if (i % 2 === 0) return <Figures key={i} text={part} />
    const inner = part.slice(1, -1)
    return part.startsWith('*') ? <strong key={i} className="font-bold"><Figures text={inner} /></strong>
      : <em key={i}><Figures text={inner} /></em>
  })
}

export default function AnswerText({ text }) {
  const blocks = (text || '').split(/\n{2,}/)
  return (
    <div className="min-w-0 max-w-[68ch] space-y-3 break-words">
      {blocks.map((block, bi) => {
        const lines = block.split('\n').filter((l) => l.trim())
        if (!lines.length) return null
        if (lines[0].startsWith('📄')) {
          return (
            <p key={bi} className="border-l-2 border-line pl-3 text-sm text-ink-soft">
              <Inline text={lines.join(' ').replace(/^📄\s*/, '')} />
            </p>
          )
        }
        const bullets = lines.filter((l) => /^\s*[•\-]\s/.test(l))
        if (bullets.length && bullets.length >= lines.length - 1) {
          const head = /^\s*[•\-]\s/.test(lines[0]) ? null : lines[0]
          return (
            <div key={bi}>
              {head && <p className="font-medium"><Inline text={head} /></p>}
              <ul className="mt-1 space-y-1">
                {bullets.map((l, li) => (
                  <li key={li} className="flex gap-2">
                    <span aria-hidden className="text-green">•</span>
                    <span className="min-w-0"><Inline text={l.replace(/^\s*[•\-]\s/, '')} /></span>
                  </li>
                ))}
              </ul>
            </div>
          )
        }
        return (
          <p key={bi}>
            {lines.map((l, li) => (
              <span key={li}>{li > 0 && <br />}<Inline text={l} /></span>
            ))}
          </p>
        )
      })}
    </div>
  )
}
