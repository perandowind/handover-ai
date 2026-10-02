from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from app.core.exceptions import AppError
from app.llm.errors import LLMResponseInvalidError

if TYPE_CHECKING:
    from app.llm.client import StructuredLLMClient
    from app.schemas.question import QuestionGenerationRequest
    from app.services.question_context import QuestionContext

from app.core.config import Settings
from app.llm.prompts.question_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import QuestionGenerationResult


def configure(settings: Settings) -> TaskDefinition[QuestionGenerationResult]:
    return TaskDefinition(
        name='question_generation', model=settings.question_model, system_prompt=SYSTEM_PROMPT,
        response_schema=QuestionGenerationResult, validation_retries=1,
    )


class QuestionValidationError(ValueError):
    pass


class QuestionGenerationTask:
    def __init__(self, client: StructuredLLMClient, definition: TaskDefinition[QuestionGenerationResult]):
        self.client = client
        self.definition = replace(definition, validation_retries=0)

    async def generate(self, request: QuestionGenerationRequest, context: QuestionContext) -> QuestionGenerationResult:
        feedback = None
        for attempt in range(2):
            payload = {'request': request.prompt, 'count': request.count, 'question_type': request.question_type,
                       'context': context.text, 'allowed_source_section_ids': list(context.source_documents),
                       'context_truncated': context.truncated, 'previous_validation_error': feedback}
            try:
                result = await self.client.generate(task=self.definition, user_prompt=json.dumps(payload, ensure_ascii=False))
                if len(result.questions) != request.count:
                    raise QuestionValidationError('QUESTION_COUNT_MISMATCH')
                seen = set()
                for question in result.questions:
                    if question.question_type != request.question_type:
                        raise QuestionValidationError('QUESTION_TYPE_MISMATCH')
                    if question.source_section_id not in context.source_documents:
                        raise QuestionValidationError('QUESTION_SOURCE_NOT_IN_CONTEXT')
                    normalized = ' '.join(question.question.split()).casefold()
                    if normalized in seen:
                        raise QuestionValidationError('DUPLICATE_QUESTION')
                    seen.add(normalized)
                return result
            except LLMResponseInvalidError:
                feedback = 'INVALID_JSON_OR_SCHEMA'
            except QuestionValidationError as exc:
                feedback = str(exc)
            logging.getLogger(__name__).warning('Question validation failed attempt=%s code=%s', attempt + 1, feedback)
        raise AppError('QUESTION_GENERATION_FAILED', '문제 검증에 두 번 실패했습니다. 다시 시도하세요.', 502,
                       {'validation_code': feedback})
