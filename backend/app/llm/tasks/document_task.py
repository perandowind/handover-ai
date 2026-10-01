from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.handover import HANDOVER_OUTLINE, NO_INFORMATION
from app.schemas.llm import GeneratedSection

if TYPE_CHECKING:
    from app.llm.client import StructuredLLMClient

from app.core.config import Settings
from app.llm.prompts.document_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import GeneratedDocument


def configure(settings: Settings) -> TaskDefinition[GeneratedDocument]:
    return TaskDefinition(
        name='document_generation', model=settings.document_model, system_prompt=SYSTEM_PROMPT,
        response_schema=GeneratedDocument, validation_retries=1,
    )


class DocumentGenerationTask:
    def __init__(self, client: StructuredLLMClient, definition: TaskDefinition[GeneratedDocument]):
        self.client = client
        self.definition = definition

    async def generate(self, prompt: str, context: str, *, context_truncated: bool = False) -> GeneratedDocument:
        if not context.strip():
            # No evidence means no opportunity for the model to invent facts.
            return GeneratedDocument(title='인수인계서', sections=[
                GeneratedSection(section_type=key, title=title, content=NO_INFORMATION)
                for key, title in HANDOVER_OUTLINE
            ])
        user_prompt = json.dumps({
            'user_request': prompt,
            'retrieved_context': context,
            'context_truncated': context_truncated,
            'target_outline': [{'section_type': key, 'title': title} for key, title in HANDOVER_OUTLINE],
            'missing_information': NO_INFORMATION,
        }, ensure_ascii=False)
        return await self.client.generate(task=self.definition, user_prompt=user_prompt)
