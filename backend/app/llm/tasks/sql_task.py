from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.exceptions import AppError
from app.llm.errors import LLMResponseInvalidError
from app.llm.prompts.sql_generation import SYSTEM_PROMPT
from app.llm.tasks.base import TaskDefinition
from app.retrieval.schema import RetrievalSchema
from app.retrieval.validator import SQLValidationError, SQLValidator, ValidatedSQL
from app.schemas.llm import SQLGenerationOutput

if TYPE_CHECKING:
    from app.llm.client import StructuredLLMClient

logger = logging.getLogger(__name__)


def configure(settings: Settings) -> TaskDefinition[SQLGenerationOutput]:
    return TaskDefinition(
        name='sql_generation', model=settings.sql_model, system_prompt=SYSTEM_PROMPT,
        response_schema=SQLGenerationOutput, validation_retries=1,
    )


class SQLGenerationTask:
    """Two total attempts across JSON/schema and SQL validation, before any I/O."""

    def __init__(self, client: StructuredLLMClient, definition: TaskDefinition[SQLGenerationOutput],
                 schema: RetrievalSchema, validator: SQLValidator):
        self.client = client
        # This workflow owns the single retry budget, rather than nesting retries.
        self.definition = replace(definition, validation_retries=0)
        self.schema = schema
        self.validator = validator

    async def generate(self, query: str, *, document_ids: list[int] | None = None) -> ValidatedSQL:
        feedback = None
        for attempt in range(2):
            prompt = json.dumps({
                'request': query,
                'document_ids': document_ids,
                'schema': self.schema.describe(),
                'max_rows': self.validator.max_rows,
                'previous_validation_error': feedback,
            }, ensure_ascii=False)
            try:
                output = await self.client.generate(task=self.definition, user_prompt=prompt)
                logger.debug('Generated retrieval SQL: %s', output.sql)
                validated = self.validator.validate(output.sql, document_ids=document_ids)
                logger.info('SQL validation passed attempt=%s', attempt + 1)
                return validated
            except (LLMResponseInvalidError, SQLValidationError) as exc:
                feedback = exc.code
                logger.warning('SQL generation validation failed attempt=%s code=%s', attempt + 1, feedback)
        raise AppError('SQL_GENERATION_FAILED', 'SQL validation failed after one regeneration',
                       502, {'attempts': 2, 'validation_code': feedback})
