import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { isProcessing, statusLabel, type DocumentSummary } from '../types/document'

export default function Documents() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    setLoading(true)
    async function load() {
      try {
        const rows = await api<DocumentSummary[]>(`/documents?limit=20&offset=${offset}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setDocuments(rows)
        setError('')
        if (rows.some(isProcessing)) timer = setTimeout(load, 2000)
      } catch (error) {
        if (!controller.signal.aborted) setError(errorMessage(error))
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [offset, revision])

  return <section>
    <div className="toolbar"><h1>문서 목록</h1><button onClick={() => setRevision(value => value + 1)}>새로고침</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <p role="status">불러오는 중…</p> : documents.length === 0 ? <p>등록된 문서가 없습니다. <Link to="/upload">PDF 업로드</Link></p> :
      <div className="table-scroll"><table><thead><tr><th>문서</th><th>OCR</th><th>구조화</th></tr></thead>
        <tbody>{documents.map(doc => <tr key={doc.id}>
          <td><Link to={`/documents/${doc.id}`}>{doc.title}</Link><small>{doc.source_filename}</small></td>
          <td>{statusLabel[doc.ocr_status]}</td><td>{statusLabel[doc.parse_status]}</td>
        </tr>)}</tbody>
      </table></div>}
    <div className="toolbar pagination">
      <button disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - 20))}>이전</button>
      <span>{offset / 20 + 1} 페이지</span>
      <button disabled={documents.length < 20 || loading} onClick={() => setOffset(value => value + 20)}>다음</button>
    </div>
  </section>
}
