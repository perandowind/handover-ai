import string

from app.schemas.llm import LLMScoringResult
from app.schemas.question import QuestionData

_ENGLISH_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def normalize_answer(value: str) -> str:
    return ' '.join(value.split()).translate(_ENGLISH_LOWER)


def score_fallback(question: QuestionData, answer: str) -> LLMScoringResult:
    if question.question_type == 'multiple_choice':
        correct = answer == question.correct_answer
        rule = '객관식 선택 번호 exact match'
    else:
        correct = normalize_answer(answer) == normalize_answer(question.correct_answer)
        rule = '앞뒤 공백 제거·영문 소문자화·연속 공백 정리 후 exact match'
    return LLMScoringResult(score=100 if correct else 0, is_correct=correct,
                           reason=f'LLM 채점 실패로 Python fallback을 사용했습니다. {rule}: {"일치" if correct else "불일치"}.')
