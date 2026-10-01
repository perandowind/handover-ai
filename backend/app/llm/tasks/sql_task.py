from app.core.config import Settings
from app.llm.prompts.sql_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import SQLGenerationOutput


def configure(settings: Settings) -> TaskDefinition[SQLGenerationOutput]:
    return TaskDefinition(
        name='sql_generation', model=settings.sql_model, system_prompt=SYSTEM_PROMPT,
        response_schema=SQLGenerationOutput, validation_retries=1,
    )
