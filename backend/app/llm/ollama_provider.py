import asyncio
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.llm.errors import LLMProviderError, LLMResponseInvalidError
from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class _Message(BaseModel):
    model_config = ConfigDict(strict=True)
    role: Literal['assistant']
    content: str = Field(min_length=1)

    @field_validator('content')
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Empty response content')
        return value


class _ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    message: _Message
    done: bool
    done_reason: str | None = None


class OllamaLLMProvider(LLMProvider):
    """Ollama REST adapter; the supplied AsyncClient is owned by the caller.

    No SDK, automatic model download, transport retry, or business logic here.
    """
    def __init__(self, *, client: httpx.AsyncClient, base_url: str, timeout_seconds: float):
        if timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be positive')
        self._client = client
        self._chat_url = f'{base_url.rstrip("/")}/api/chat'
        self._timeout_seconds = timeout_seconds

    async def generate(
        self, *, model: str, system_prompt: str, user_prompt: str,
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'stream': False,
        }
        if response_schema is not None:
            payload['format'] = response_schema.model_json_schema()
        try:
            # HTTPX has per-I/O timeouts; asyncio also bounds the entire request.
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.post(
                    self._chat_url, json=payload,
                    timeout=httpx.Timeout(self._timeout_seconds),
                    follow_redirects=False,
                )
        except (httpx.TimeoutException, TimeoutError):
            logger.warning('Ollama request failed code=OLLAMA_TIMEOUT')
            raise LLMProviderError('OLLAMA_TIMEOUT', 'LLM 요청 시간이 초과되었습니다.', 504) from None
        except httpx.RequestError:
            logger.warning('Ollama request failed code=OLLAMA_UNAVAILABLE')
            raise LLMProviderError('OLLAMA_UNAVAILABLE', 'LLM 서버에 연결할 수 없습니다.', 503) from None

        if not response.is_success:
            code, status, message = 'OLLAMA_REQUEST_FAILED', 502, 'LLM 서버 요청에 실패했습니다.'
            if response.status_code == 404:
                code, status, message = 'OLLAMA_MODEL_NOT_FOUND', 503, 'LLM 모델 또는 엔드포인트를 찾을 수 없습니다.'
            elif response.status_code == 429:
                code, status, message = 'OLLAMA_BUSY', 503, 'LLM 서버가 요청을 처리할 수 없습니다. 잠시 후 다시 시도하세요.'
            logger.warning('Ollama request failed code=%s upstream_status=%s', code, response.status_code)
            raise LLMProviderError(code, message, status, {'upstream_status': response.status_code})
        try:
            envelope = response.json()
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise LLMResponseInvalidError('envelope') from None
        if isinstance(envelope, dict) and 'error' in envelope:
            raise LLMProviderError('OLLAMA_REQUEST_FAILED', 'LLM 모델 실행에 실패했습니다.', 502)
        try:
            parsed = _ChatResponse.model_validate(envelope)
        except ValidationError as exc:
            raise LLMResponseInvalidError('envelope', error_count=exc.error_count()) from None
        if not parsed.done or parsed.done_reason not in (None, 'stop'):
            # A valid-looking JSON prefix from a truncated generation is not complete.
            raise LLMResponseInvalidError('envelope')
        # Thinking metadata is deliberately not treated as the model's answer.
        return parsed.message.content
