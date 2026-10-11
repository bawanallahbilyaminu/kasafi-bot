import { useCallback, useEffect, useRef, useState } from 'react'

// Voice notes in the browser: MediaRecorder + live level bars from an AnalyserNode.
const MAX_SECONDS = 120

function pickType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return types.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || ''
}

export default function useRecorder({ onDone }) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [levels, setLevels] = useState(() => Array(5).fill(0.15))
  const [error, setError] = useState(null)
  const rec = useRef(null)

  const cleanup = useCallback(() => {
    const r = rec.current
    if (!r) return
    cancelAnimationFrame(r.raf)
    clearInterval(r.timer)
    r.stream.getTracks().forEach((t) => t.stop())
    r.ctx?.close().catch(() => {})
    rec.current = null
    setRecording(false)
    setSeconds(0)
    setLevels(Array(5).fill(0.15))
  }, [])

  useEffect(() => cleanup, [cleanup])

  const stop = useCallback((send = true) => {
    const r = rec.current
    if (!r) return
    r.send = send
    if (r.mr.state !== 'inactive') r.mr.stop()
  }, [])

  const start = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Wannan burauzar ba ta iya daukar murya. Gwada Chrome ko Safari na zamani.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const type = pickType()
      const mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
      const chunks = []
      const r = { mr, stream, chunks, send: true, started: Date.now() }
      rec.current = r
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      mr.onstop = () => {
        const blob = new Blob(chunks, { type: mr.mimeType || type || 'audio/webm' })
        const long = Date.now() - r.started > 700
        const send = r.send
        cleanup()
        if (send && long && blob.size > 1000) onDone(blob)
        else if (send) setError('Sakon ya yi gajere. Danna makirufo, yi magana, sannan ku danna don aikawa.')
      }
      // level meter
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)()
        const an = ctx.createAnalyser()
        an.fftSize = 64
        ctx.createMediaStreamSource(stream).connect(an)
        const data = new Uint8Array(an.frequencyBinCount)
        r.ctx = ctx
        const tick = () => {
          an.getByteFrequencyData(data)
          const bands = [2, 4, 6, 9, 13].map((i) => Math.min(1, Math.max(0.12, data[i] / 200)))
          setLevels(bands)
          r.raf = requestAnimationFrame(tick)
        }
        tick()
      } catch { /* bars are decoration only */ }
      r.timer = setInterval(() => {
        const s = Math.floor((Date.now() - r.started) / 1000)
        setSeconds(s)
        if (s >= MAX_SECONDS) stop(true)
      }, 250)
      mr.start(250)
      setRecording(true)
    } catch (e) {
      cleanup()
      setError(e?.name === 'NotAllowedError'
        ? 'An hana amfani da makirufo. Ba da izini a saitin burauza, sannan a sake gwadawa.'
        : 'Ba a iya bude makirufo ba.')
    }
  }, [cleanup, onDone, stop])

  return { recording, seconds, levels, error, start, stop, clearError: () => setError(null) }
}
