from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Request

from app.core.config import Settings
from app.llm.client import StructuredLLMClient
from app.llm.ollama_provider import OllamaLLMProvider
from app.llm.provider import LLMProvider


@asynccontextmanager
async def managed_provider(settings: Settings, injected: LLMProvider | None = None) -> AsyncIterator[LLMProvider]:
    if injected is not None:
        # The caller owns injected resources, including fake providers in tests.
        yield injected
    else:
        # Constructing a client never connects to Ollama. Ignore ambient proxy
        # variables so local document content stays on the configured direct URL.
        async with httpx.AsyncClient(trust_env=False) as client:
            yield OllamaLLMProvider(client=client, base_url=settings.ollama_base_url,
                                    timeout_seconds=settings.ollama_timeout_seconds)


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider


def get_llm_client(request: Request) -> StructuredLLMClient:
    return request.app.state.llm_client
