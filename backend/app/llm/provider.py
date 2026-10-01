from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        """Return untrusted response content. Structured callers must validate it.

        Implementations must raise LLMError for provider/response failures and
        propagate cancellation. The composition layer owns transport resources.
        """
        raise NotImplementedError
