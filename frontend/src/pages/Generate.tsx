import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import GeneratedDocumentPreview from '../components/GeneratedDocumentPreview'
import type { DocumentSummary } from '../types/document'
import type { GeneratedDocument } from '../types/generation'

export default function Generate() {
  const [prompt, setPrompt] = useState('')
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<GeneratedDocument | null>(null)
  const generationRequest = useRef<AbortController | null>(null)

  useEffect(() => () => generationRequest.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setListError('')
    api<DocumentSummary[]>(`/documents?limit=20&offset=${offset}`, { signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) setDocuments(rows) })
      .catch(error => { if (!controller.signal.aborted) setListError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [offset, revision])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!prompt.trim() || generationRequest.current) return
    const controller = new AbortController()
    generationRequest.current = controller
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const document = await api<GeneratedDocument>('/generation/handover', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), document_ids: selectedIds.length ? selectedIds : null }),
        signal: controller.signal,
      })
      if (!controller.signal.aborted) setResult(document)
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      generationRequest.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <section>
    <h1>인수인계서 생성</h1>
    <p>저장된 문서에서 관련 내용을 찾아 기본 8개 목차의 인수인계서 초안을 작성합니다.</p>
    <form onSubmit={submit} className="generation-form" aria-busy={busy}>
      <label htmlFor="generation-prompt">작성 요청</label>
      <textarea id="generation-prompt" rows={4} required maxLength={4000} disabled={busy}
        placeholder="DB 운영 업무를 담당할 신규 인계자를 위한 인수인계서를 작성해줘."
        value={prompt} onChange={event => setPrompt(event.target.value)} />
      <small>근거가 없는 항목은 “관련 정보 없음”으로 표시됩니다.</small>
      <fieldset disabled={busy}>
        <legend>대상 문서 (선택 사항)</legend>
        <p className="muted">선택하지 않으면 전체 문서에서 검색합니다. OCR과 구조화가 완료된 문서만 선택할 수 있습니다.</p>
        {loading ? <p role="status">문서 불러오는 중…</p> : listError ?
          <div><p role="alert" className="error">{listError}</p><button type="button" onClick={() => setRevision(value => value + 1)}>다시 불러오기</button></div> :
          documents.length === 0 ? <p>등록된 문서가 없습니다.</p> :
            <div className="document-choices">{documents.map(doc => {
              const ready = doc.ocr_status === 'completed' && doc.parse_status === 'completed'
              const checked = selectedIds.includes(doc.id)
              return <label key={doc.id}>
                <input type="checkbox" checked={checked} disabled={!ready || (!checked && selectedIds.length >= 100)}
                  onChange={event => setSelectedIds(ids => event.target.checked ? [...ids, doc.id] : ids.filter(id => id !== doc.id))} />
                <span>{doc.title}<small>{doc.source_filename}{!ready && ' · 처리 미완료'}</small></span>
              </label>
            })}</div>}
        <div className="toolbar pagination">
          <button type="button" disabled={!offset || loading} onClick={() => setOffset(value => Math.max(0, value - 20))}>이전</button>
          <span>{offset / 20 + 1} 페이지</span>
          <button type="button" disabled={documents.length < 20 || loading || !!listError} onClick={() => setOffset(value => value + 20)}>다음</button>
        </div>
        <p>선택한 문서: {selectedIds.length}개 (최대 100개)</p>
        {selectedIds.length > 0 && <button type="button" onClick={() => setSelectedIds([])}>선택 해제</button>}
      </fieldset>
      <button disabled={busy || !prompt.trim()}>{busy ? '생성 중…' : '인수인계서 생성'}</button>
    </form>
    {busy && <p role="status">관련 내용을 조회하고 인수인계서를 작성하고 있습니다. 모델에 따라 수 분이 걸릴 수 있습니다.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {result && <GeneratedDocumentPreview document={result} />}
  </section>
}
