from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.client import StructuredLLMClient
    from app.schemas.question import QuestionData

from app.core.config import Settings
from app.llm.prompts.scoring import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import LLMScoringResult


def configure(settings: Settings) -> TaskDefinition[LLMScoringResult]:
    return TaskDefinition(
        name='scoring', model=settings.scoring_model, system_prompt=SYSTEM_PROMPT,
        response_schema=LLMScoringResult, validation_retries=0,
    )


class ScoringTask:
    def __init__(self, client: StructuredLLMClient, definition: TaskDefinition[LLMScoringResult]):
        self.client = client
        # Scoring must fail directly to Python; no correction retry.
        self.definition = replace(definition, validation_retries=0)

    async def score(self, question: QuestionData, answer: str) -> LLMScoringResult:
        payload = {
            'question_type': question.question_type, 'question': question.question_text,
            'choices': question.choices, 'correct_answer': question.correct_answer,
            'explanation': question.explanation, 'user_answer': answer,
        }
        return await self.client.generate(task=self.definition, user_prompt=json.dumps(payload, ensure_ascii=False))
