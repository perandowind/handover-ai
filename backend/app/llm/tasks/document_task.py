from app.core.config import Settings
from app.llm.prompts.document_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import GeneratedDocument


def configure(settings: Settings) -> TaskDefinition[GeneratedDocument]:
    return TaskDefinition(
        name='document_generation', model=settings.document_model, system_prompt=SYSTEM_PROMPT,
        response_schema=GeneratedDocument, validation_retries=1,
    )
