from app.core.config import Settings
from app.llm.prompts.scoring import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import LLMScoringResult


def configure(settings: Settings) -> TaskDefinition[LLMScoringResult]:
    return TaskDefinition(
        name='scoring', model=settings.scoring_model, system_prompt=SYSTEM_PROMPT,
        response_schema=LLMScoringResult, validation_retries=0,
    )
