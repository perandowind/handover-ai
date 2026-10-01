from typing import Literal

from app.core.exceptions import AppError


class LLMError(AppError):
    """Shared failure type for future service policies, including scoring fallback."""


class LLMProviderError(LLMError):
    """Connection, timeout, HTTP status, or model execution failure."""


class LLMResponseInvalidError(LLMError):
    def __init__(self, stage: Literal['envelope', 'json', 'schema'], *, error_count: int = 1):
        super().__init__(
            code='LLM_RESPONSE_INVALID', message='LLM 응답 형식이 올바르지 않습니다.',
            status_code=502, detail={'stage': stage, 'error_count': error_count},
        )
