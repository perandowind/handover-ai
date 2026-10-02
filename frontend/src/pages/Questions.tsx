import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import QuestionList from '../components/QuestionList'
import type { DocumentSummary } from '../types/document'
import type { Question } from '../types/question'

export default function Questions() {
  const [prompt, setPrompt] = useState('주요 업무와 주의사항을 중심으로 문제를 만들어줘.')
  const [count, setCount] = useState(5)
  const [type, setType] = useState<Question['question_type']>('multiple_choice')
  const [documentId, setDocumentId] = useState('')
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [listError, setListError] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [revision, setRevision] = useState(0)
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api<DocumentSummary[]>('/documents?limit=100', { signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) setDocuments(rows) })
      .catch(error => { if (!controller.signal.aborted) setListError(errorMessage(error)) })
    return () => { controller.abort(); active.current?.abort() }
  }, [])
  async function generate(event: FormEvent) {
    event.preventDefault()
    if (!prompt.trim() || active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true); setError(''); setSuccess('')
    try {
      const rows = await api<Question[]>('/questions/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ prompt, count, question_type: type, document_ids: documentId ? [Number(documentId)] : null }),
      })
      if (!controller.signal.aborted) { setSuccess(`${rows.length}개 문제를 생성하고 저장했습니다.`); setRevision(value => value + 1) }
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return <section>
    <h1>문제 생성</h1>
    <p>저장된 문서의 원천 섹션을 바탕으로 문제와 정답·해설을 만듭니다.</p>
    <form onSubmit={generate} aria-busy={busy}>
      <label htmlFor="question-prompt">출제 요청</label>
      <textarea id="question-prompt" rows={3} required maxLength={4000} disabled={busy} value={prompt} onChange={event => setPrompt(event.target.value)} />
      <label htmlFor="question-document">대상 문서 (선택 사항 · 최근 100개)</label>
      <select id="question-document" disabled={busy} value={documentId} onChange={event => setDocumentId(event.target.value)}>
        <option value="">전체 문서에서 검색</option>
        {documents.map(doc => <option key={doc.id} value={doc.id} disabled={doc.ocr_status !== 'completed' || doc.parse_status !== 'completed'}>{doc.title} (#{doc.id})</option>)}
      </select>
      {listError && <p role="alert" className="error">문서 목록: {listError}</p>}
      <label htmlFor="question-type">문제 유형</label>
      <select id="question-type" disabled={busy} value={type} onChange={event => setType(event.target.value as Question['question_type'])}>
        <option value="multiple_choice">객관식</option><option value="short_answer">단답형</option>
      </select>
      <label htmlFor="question-count">문제 수 (1~20)</label>
      <input id="question-count" type="number" min={1} max={20} required disabled={busy} value={count} onChange={event => setCount(Number(event.target.value))} />
      <button disabled={busy || !prompt.trim()}>{busy ? '문제 생성 중…' : '문제 생성 및 저장'}</button>
    </form>
    {busy && <p role="status">관련 섹션을 조회하고 문제를 생성하고 있습니다.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {success && <p role="status">{success}</p>}
    <QuestionList key={revision} />
  </section>
}
