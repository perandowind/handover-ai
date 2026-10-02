import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api/client'
import type { Question } from '../types/question'
import QuestionCard from './QuestionCard'

export default function QuestionList({ revealAnswers = true }: { revealAnswers?: boolean }) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    api<Question[]>(`/questions?offset=${offset}&limit=20`, { signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) setQuestions(rows) })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [offset, revision])
  return <section aria-label="저장된 문제">
    <div className="toolbar"><h2>저장된 문제</h2><button onClick={() => setRevision(value => value + 1)}>새로고침</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <p role="status">문제 불러오는 중…</p> : !error && (questions.length ?
      questions.map(question => <QuestionCard key={question.id} question={question} revealAnswers={revealAnswers} />) : <p>저장된 문제가 없습니다.</p>)}
    <div className="toolbar pagination">
      <button disabled={loading || !offset} onClick={() => setOffset(value => Math.max(0, value - 20))}>이전</button>
      <span>{offset / 20 + 1} 페이지</span>
      <button disabled={loading || !!error || questions.length < 20} onClick={() => setOffset(value => value + 20)}>다음</button>
    </div>
  </section>
}
