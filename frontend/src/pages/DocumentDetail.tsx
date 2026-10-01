import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { isProcessing, statusLabel, type DocumentDetail as Detail } from '../types/document'

export default function DocumentDetail() {
  const { id } = useParams()
  const [document, setDocument] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    setDocument(null)
    setError('')
    async function load() {
      try {
        const doc = await api<Detail>(`/documents/${id}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setDocument(doc)
        setError('')
        if (isProcessing(doc)) timer = setTimeout(load, 2000)
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      }
    }
    void load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [id, revision])

  return <section>
    <Link to="/">← 문서 목록</Link>
    {error && <p role="alert" className="error">{error} <button onClick={() => setRevision(x => x + 1)}>다시 조회</button></p>}
    {!document ? !error && <p role="status">불러오는 중…</p> : <>
      <h1>{document.title}</h1>
      <p role="status">OCR: {statusLabel[document.ocr_status]} · 구조화: {statusLabel[document.parse_status]} · 저장 페이지: {document.pages.length}</p>
      {isProcessing(document) && <p>분석 중입니다. 상태가 자동 갱신됩니다. 최초 실행은 모델 준비로 더 오래 걸릴 수 있습니다.</p>}
      {document.processing_error && <p role="alert" className="error">{document.processing_error.message} ({document.processing_error.code})</p>}
      <h2>구조화된 목차</h2>
      {document.sections.length === 0 && <p>아직 구조화된 내용이 없습니다.</p>}
      {document.sections.map(section => <article key={section.id}>
        <h3>{section.sequence}. {section.section_title} <small>원문 {section.source_page}페이지</small></h3>
        <p className="preserve">{section.content || '(내용 없음)'}</p>
      </article>)}
      <h2>업무 항목</h2>
      {document.handover_items.length === 0 && <p>저장된 업무 항목이 없습니다.</p>}
      {document.handover_items.map(item => <details key={item.id}>
        <summary>{item.task_name}</summary><p className="preserve">{item.description}</p>
        <dl>{([['절차', item.procedure], ['주의사항', item.precaution], ['주기', item.frequency],
          ['시스템', item.related_system], ['연락처', item.contact_info], ['중요도', item.importance]] as const)
          .filter(([, value]) => value !== null).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="preserve">{value}</dd></div>)}</dl>
      </details>)}
      <h2>페이지별 OCR 원본</h2>
      {document.pages.map(page => <article key={page.id}>
        <h3>{page.page_number}페이지</h3><pre>{page.raw_text || '(인식된 텍스트 없음 또는 처리 중)'}</pre>
        <details><summary>신뢰도 및 bounding box</summary>
          {(page.ocr_json.lines ?? []).map((line, index) => <p key={index}>{line.text} · {(line.confidence * 100).toFixed(1)}%<br /><code>{JSON.stringify(line.bbox)}</code></p>)}
        </details>
        <details><summary>Raw JSON 보기</summary><pre>{JSON.stringify(page.ocr_json, null, 2)}</pre></details>
      </article>)}
    </>}
  </section>
}
