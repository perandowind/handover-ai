import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import QuestionList from '../components/QuestionList'
import type { Question, ScoringResult } from '../types/question'

function QuizQuestion({ id }: { id: string }) {
  const [question, setQuestion] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ScoringResult | null>(null)
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api<Question>(`/questions/${id}`, { signal: controller.signal })
      .then(row => { if (!controller.signal.aborted) setQuestion(row) })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => { controller.abort(); active.current?.abort() }
  }, [id])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!question || !answer.trim() || active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true); setError(''); setResult(null)
    try {
      const score = await api<ScoringResult>('/scoring/evaluate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ question_id: question.id, answer }),
      })
      if (!controller.signal.aborted) setResult(score)
    } catch (error) {
      if (!controller.signal.aborted) setError(errorMessage(error))
    } finally {
      active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return <section>
    <h1>Quiz · 문제 {id}</h1>
    <Link to="/quiz">문제 선택으로 돌아가기</Link>
    {loading && <p role="status">문제를 불러오는 중…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {question && <form onSubmit={submit} aria-busy={busy}>
      <p className="preserve">{question.question_text}</p>
      {question.question_type === 'multiple_choice' ? <fieldset disabled={busy}>
        <legend>정답 선택</legend>
        {question.choices?.map((choice, index) => <label className="quiz-choice" key={index}>
          <input type="radio" name="answer" value={String(index + 1)} checked={answer === String(index + 1)}
            onChange={event => { setAnswer(event.target.value); setResult(null) }} />
          <span className="preserve">{index + 1}. {choice}</span>
        </label>)}
      </fieldset> : <><label htmlFor="quiz-answer">답안</label><textarea id="quiz-answer" required maxLength={4000} disabled={busy}
        value={answer} onChange={event => { setAnswer(event.target.value); setResult(null) }} /></>}
      <button disabled={busy || !answer.trim()}>{busy ? '채점 중…' : '답안 제출'}</button>
    </form>}
    {busy && <p role="status">LLM으로 채점하고 있습니다. 실패하면 Python fallback으로 채점합니다.</p>}
    {result && <article aria-label="채점 결과">
      <h2>점수: {result.score} / 100</h2>
      <p>판정: {result.is_correct === null ? '미지정' : result.is_correct ? '정답' : '오답'}</p>
      <p>채점 방식: {result.scoring_method === 'llm' ? 'LLM' : 'Python fallback'}</p>
      <p className="preserve">{result.reason}</p>
    </article>}
  </section>
}

export default function Quiz() {
  const { id } = useParams()
  return id ? <QuizQuestion key={id} id={id} /> : <section><h1>Quiz</h1><p>풀 문제를 선택하세요. <Link to="/questions">새 문제 생성</Link></p><QuestionList revealAnswers={false} /></section>
}
