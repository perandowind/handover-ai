"""Infrastructure-only probe. Default: mock HTTP; --live: configured Ollama server.

Run from backend: uv run python scripts/smoke_llm.py [--live]
No SQL/document generation, retrieval, database writes, or model downloads.
"""
import argparse
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx

from app.core.config import Settings
from app.llm.client import StructuredLLMClient
from app.llm.dependencies import managed_provider
from app.llm.errors import LLMError
from app.llm.ollama_provider import OllamaLLMProvider
from app.llm.tasks.base import TaskDefinition
from app.schemas.llm import LLMOutput


class ProbeResult(LLMOutput):
    status: Literal['ok']


async def run(live: bool) -> dict:
    settings = Settings()
    async with AsyncExitStack() as stack:
        injected = None
        if not live:
            def handler(request: httpx.Request) -> httpx.Response:
                payload = json.loads(request.content)
                assert request.url.path.endswith('/api/chat')
                assert payload['stream'] is False and payload['format'] == ProbeResult.model_json_schema()
                return httpx.Response(200, json={
                    'message': {'role': 'assistant', 'content': '{"status":"ok"}'},
                    'done': True, 'done_reason': 'stop',
                })
            client = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            injected = OllamaLLMProvider(client=client, base_url=settings.ollama_base_url,
                                        timeout_seconds=settings.ollama_timeout_seconds)
        provider = await stack.enter_async_context(managed_provider(settings, injected))
        result = await StructuredLLMClient(provider).generate(
            task=TaskDefinition(name='infrastructure_probe', model=settings.sql_model,
                                system_prompt='Return the JSON object {"status":"ok"}.',
                                response_schema=ProbeResult),
            user_prompt='Check structured JSON output only.',
        )
        return {'mode': 'live' if live else 'mock', 'model': settings.sql_model, 'result': result.model_dump()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Contact configured Ollama using SQL_MODEL for a JSON-only probe')
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args.live)), ensure_ascii=False, indent=2))
        return 0
    except LLMError as exc:
        print(json.dumps({'code': exc.code, 'message': exc.message, 'detail': exc.detail}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
