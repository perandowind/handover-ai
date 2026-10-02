export interface Question {
  id: number
  document_id: number | null
  section_id: number | null
  question_type: 'multiple_choice' | 'short_answer'
  question_text: string
  choices: string[] | null
  created_at: string
}
export interface QuestionAnswer { correct_answer: string; explanation: string | null }
export interface ScoringResult {
  id: number; question_id: number; score: number; is_correct: boolean | null
  reason: string; scoring_method: 'llm' | 'python_fallback'
}
