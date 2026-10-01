from app.core.config import Settings
from app.llm.prompts.question_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import QuestionGenerationResult


def configure(settings: Settings) -> TaskDefinition[QuestionGenerationResult]:
    return TaskDefinition(
        name='question_generation', model=settings.question_model, system_prompt=SYSTEM_PROMPT,
        response_schema=QuestionGenerationResult, validation_retries=1,
    )
