import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'

export default function Upload() {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setError('')
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('PDF 파일을 선택하세요.')
      return
    }
    setBusy(true)
    const data = new FormData()
    data.append('file', file)
    try {
      const result = await api<{ document_id: number }>('/documents/upload', { method: 'POST', body: data })
      navigate(`/documents/${result.document_id}`)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return <section>
    <h1>스캔 PDF 업로드</h1>
    <p>페이지를 이미지로 변환한 뒤 한국어 OCR과 목차 구조화를 수행합니다.</p>
    <p className="muted">기본 제한: PDF 50 MB · 30페이지. 암호화된 파일은 지원하지 않습니다.</p>
    <form onSubmit={submit}>
      <label htmlFor="pdf">인수인계서 PDF</label>
      <input id="pdf" type="file" accept=".pdf,application/pdf" disabled={busy}
        onChange={event => setFile(event.target.files?.[0] ?? null)} />
      <button disabled={!file || busy}>{busy ? '업로드 중…' : '업로드 및 분석'}</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
  </section>
}
