import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Question, QuestionAnswer } from '../types/question'

export default function QuestionCard({ question, revealAnswers = true }: { question: Question; revealAnswers?: boolean }) {
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null)
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  async function toggleAnswer() {
    if (answer) { setVisible(value => !value); return }
    if (active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true); setError('')
    try {
      const result = await api<QuestionAnswer>(`/questions/${question.id}/answer`, { signal: controller.signal })
      if (!controller.signal.aborted) { setAnswer(result); setVisible(true) }
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return <article>
    <h3>문제 {question.id} · {question.question_type === 'multiple_choice' ? '객관식' : '단답형'}</h3>
    <p className="preserve">{question.question_text}</p>
    {question.choices && <ol>{question.choices.map((choice, index) => <li key={index} className="preserve">{choice}</li>)}</ol>}
    {question.document_id && <p><Link to={`/documents/${question.document_id}`}>원천 문서 #{question.document_id}</Link> · 섹션 #{question.section_id}</p>}
    <div className="toolbar">
      <Link to={`/quiz/${question.id}`}>문제 풀기</Link>
      {revealAnswers && <button type="button" disabled={busy} aria-expanded={visible} onClick={() => void toggleAnswer()}>
        {busy ? '불러오는 중…' : visible ? '정답·해설 숨기기' : '정답·해설 보기'}
      </button>}
    </div>
    {error && <p role="alert" className="error">{error}</p>}
    {visible && answer && <div className="preserve"><p>정답: {question.question_type === 'multiple_choice' ? `${answer.correct_answer}번` : answer.correct_answer}</p><p>해설: {answer.explanation ?? '관련 정보 없음'}</p></div>}
  </article>
}
