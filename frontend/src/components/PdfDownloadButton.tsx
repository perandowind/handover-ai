import { useEffect, useRef, useState } from 'react'
import { apiPdf, errorMessage } from '../api/client'
import type { GeneratedDocument } from '../types/generation'

export default function PdfDownloadButton({ document: generated }: { document: GeneratedDocument }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    setBusy(false)
    setError('')
    return () => { active.current?.abort(); active.current = null }
  }, [generated])

  async function download() {
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    try {
      const pdf = await apiPdf('/generation/handover/pdf', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(generated), signal: controller.signal,
      })
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(pdf)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'handover.pdf'
      document.body.appendChild(anchor)
      try { anchor.click() } finally {
        anchor.remove()
        // Allow the browser to start reading the blob before releasing it.
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      if (active.current === controller) active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <div>
    <button type="button" disabled={busy} onClick={() => void download()}>
      {busy ? 'PDF 생성 중…' : 'PDF 다운로드'}
    </button>
    {busy && <small role="status">PDF를 준비하고 있습니다.</small>}
    {error && <p role="alert" className="error">{error}</p>}
  </div>
}
