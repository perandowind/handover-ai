import logging

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError
from app.llm.tasks.scoring_task import ScoringTask
from app.repositories.question_repository import QuestionRepository
from app.schemas.llm import LLMScoringResult
from app.schemas.scoring import ScoringRequest, ScoringResult
from app.scoring.python_fallback import score_fallback

logger = logging.getLogger(__name__)


class ScoringService:
    def __init__(self, repository: QuestionRepository, task: ScoringTask):
        self.repository, self.task = repository, task

    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        question = await run_in_threadpool(self.repository.get, request.question_id)
        if not question.correct_answer.strip():
            raise AppError('QUESTION_INVALID', '저장된 정답이 유효하지 않습니다.', 409)
        if question.question_type == 'multiple_choice':
            allowed = {str(index) for index in range(1, len(question.choices or []) + 1)}
            if not allowed or question.correct_answer not in allowed:
                raise AppError('QUESTION_INVALID', '저장된 선택지 또는 정답이 유효하지 않습니다.', 409)
            if request.answer not in allowed:
                raise AppError('INVALID_ANSWER', '선택지 번호를 답안으로 제출하세요.', 422)
        try:
            result = LLMScoringResult.model_validate(await self.task.score(question, request.answer), strict=True)
            method = 'llm'
        except Exception as exc:
            # Only the LLM call/validation is inside this boundary. DB failures
            # and cancellation must not masquerade as a successful fallback.
            logger.warning('Scoring fallback reason=%s', type(exc).__name__)
            result = score_fallback(question, request.answer)
            method = 'python_fallback'
        return await run_in_threadpool(self.repository.save_score, question.id, request.answer, result, method)
