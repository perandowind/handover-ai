import json
import logging

from app.llm.errors import LLMResponseInvalidError
from app.llm.provider import LLMProvider
from app.llm.tasks.base import TaskDefinition
from app.llm.validation import OutputT, parse_and_validate

logger = logging.getLogger(__name__)
_JSON_POLICY = '반드시 지정된 schema의 JSON 객체 하나만 반환하세요. Markdown, 설명문, 사고 과정은 출력하지 마세요.'
_RETRY_POLICY = '이전 응답의 JSON 또는 schema 검증에 실패했습니다. 필수 필드와 타입·범위를 확인하여 다시 응답하세요.'


class StructuredLLMClient:
    """Provider-independent JSON boundary. Task specs contain no business workflow."""
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(self, *, task: TaskDefinition[OutputT], user_prompt: str) -> OutputT:
        schema_json = json.dumps(task.response_schema.model_json_schema(), ensure_ascii=False)
        system_prompt = f'{task.system_prompt}\n{_JSON_POLICY}\nJSON Schema:\n{schema_json}'
        for attempt in range(task.validation_retries + 1):
            logger.info('LLM request task=%s attempt=%s', task.name, attempt + 1)
            try:
                raw = await self.provider.generate(
                    model=task.model,
                    system_prompt=system_prompt if attempt == 0 else f'{system_prompt}\n{_RETRY_POLICY}',
                    user_prompt=user_prompt,
                    response_schema=task.response_schema,
                )
                return parse_and_validate(raw, task.response_schema)
            except LLMResponseInvalidError as exc:
                logger.warning('LLM validation failed task=%s attempt=%s stage=%s',
                               task.name, attempt + 1, exc.detail['stage'])
                if attempt == task.validation_retries:
                    raise
        raise AssertionError('Unreachable retry state')
